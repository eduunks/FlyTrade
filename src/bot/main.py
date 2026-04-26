import os
import enum
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from src.database.connection import SessionLocal, init_db, bootstrap_data
from src.database.models import User, Order, OrderStatus, Program, OfferProposal, ProposalStatus, Feedback
from src.services.formatter import format_currency_custom
from src.services.config_service import get_setting

load_dotenv()

MENU, BUY_QUANTITY, BUY_PROGRAM, BUY_PASSENGERS, BUY_DEADLINE, BUY_PRICE, CONFIRM_BUY, MY_ADS, PROPOSE_CONFIRM, PROPOSE_PRICE, PROPOSE_CONFIRM_SEND, FEEDBACK_STAR, FEEDBACK_COMMENT = range(13)
REG_NAME, REG_CPF, REG_BIRTH = range(13, 16)

def get_user(telegram_id, username):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = update.effective_user
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_data.id).first()
    
    if not user:
        user = User(telegram_id=user_data.id, username=user_data.username)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.username != user_data.username:
        user.username = user_data.username
        db.commit()

    if not user.is_registered:
        await update.message.reply_text(
            "👋 Olá! Bem-vindo ao FlyTrade.\n\n"
            "Vi que este é seu primeiro acesso. Para sua segurança, precisamos de um cadastro rápido.\n\n"
            "Qual seu <b>Nome Completo</b>?",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        db.close()
        return REG_NAME

    if user.is_suspended:
        await update.message.reply_text("Sua conta está suspensa.")
        db.close()
        return ConversationHandler.END

    if context.args and context.args[0].startswith("proposal_"):
        order_id = int(context.args[0].split("_")[1])
        order = db.query(Order).filter(Order.id == order_id).first()

        if not order or order.status != OrderStatus.PENDING:
            db.close()
            await update.message.reply_text("Esta oferta não está mais disponível.")
            return ConversationHandler.END

        if order.user_id == user.id:
            db.close()
            await update.message.reply_text("Você não pode enviar proposta para sua própria oferta.")
            return ConversationHandler.END

        context.user_data["proposal_order_id"] = order.id
        context.user_data["proposal_role"] = "seller" if order.order_type == "BUY" else "buyer"

        text = (
            f"Você está prestes a enviar uma proposta para a oferta #{order.id}.\n"
            f"Programa: {order.program.name}\n"
            f"Quantidade: {order.quantity:,} milhas\n"
            f"Preço atual: {format_price_br(order.price_per_thousand)} por milheiro\n\n"
            "Deseja manter este valor ou fazer uma contraproposta?"
        )
        db.close()
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("Manter o preço", callback_data="proposal_keep")],
            [InlineKeyboardButton("Fazer contraproposta", callback_data="proposal_counter")],
            [InlineKeyboardButton("Cancelar", callback_data="proposal_cancel")],
        ])
        
        await update.message.reply_text(text, reply_markup=reply_markup)
        return ConversationHandler.END

    support_user = os.getenv("SUPPORT_USERNAME", "FlyTradeSuporte").replace("@", "")
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    profile_url = f"{base_url}/profile/{user.id}"
    
    keyboard = [
        [InlineKeyboardButton("📥 Comprar", callback_data="buy"), InlineKeyboardButton("💸 Vender", callback_data="sell")],
        [InlineKeyboardButton("📋 Minhas Ofertas", callback_data="my_ads"), InlineKeyboardButton("👤 Meu Perfil", web_app=WebAppInfo(url=profile_url))],
        [InlineKeyboardButton("💬 Suporte", url=f"https://t.me/{support_user}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "Selecione uma opção:"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        temp_msg = await update.message.reply_text("Carregando...", reply_markup=ReplyKeyboardRemove())
        await temp_msg.delete()
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        
    db.close()
    return ConversationHandler.END

async def get_reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg_name"] = update.message.text
    await update.message.reply_text("Ótimo! Agora, digite seu <b>CPF</b> (apenas números):", parse_mode='HTML')
    return REG_CPF

async def get_reg_cpf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from src.services.validators import is_valid_cpf
    cpf_input = update.message.text
    
    if not is_valid_cpf(cpf_input):
        await update.message.reply_text("⚠️ CPF inválido. Por favor, digite um CPF real para prosseguir.")
        return REG_CPF
    
    db = SessionLocal()
    cpf_exists = db.query(User).filter(User.cpf == cpf_input).first()
    db.close()
    
    if cpf_exists:
        await update.message.reply_text("⚠️ Este CPF já está cadastrado em outra conta. Por favor, digite um CPF diferente.")
        return REG_CPF
    
    context.user_data["reg_cpf"] = cpf_input
    await update.message.reply_text("Para finalizar, qual sua <b>Data de Nascimento</b>? (Ex: 01/05/1990)", parse_mode='HTML')
    return REG_BIRTH

async def get_reg_birth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birth = update.message.text
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    
    user.full_name = context.user_data["reg_name"]
    user.cpf = context.user_data["reg_cpf"]
    user.birth_date = birth
    user.is_registered = True
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        db.close()
        await update.message.reply_text("⚠️ Ocorreu um erro no cadastro (possivelmente o CPF já está em uso). Vamos tentar o CPF novamente.")
        return REG_CPF
    
    db.close()
    
    await update.message.reply_text("✅ Cadastro finalizado com sucesso!")
    return await start(update, context) 

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id) 
    admin_id = str(os.getenv("ADMIN_TELEGRAM_ID")).strip() 

    if user_id != admin_id:
        await update.message.reply_text("⚠️ Não autorizado: Apenas administradores.")
        return

    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    webapp_url = f"{base_url}/admin"
    
    keyboard = [[InlineKeyboardButton("Abrir Painel de Administração", web_app=WebAppInfo(url=webapp_url))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Painel de Administração do FlyTrade:", reply_markup=reply_markup)

async def list_my_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        
    user_data = update.effective_user
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_data.id).first()
    
    if not user:
        db.close()
        return ConversationHandler.END
        
    orders = db.query(Order).filter(Order.user_id == user.id, Order.status == OrderStatus.PENDING).all()

    if not orders:
        db.close()
        msg = "Você não possui ofertas ativas no momento."
        if query:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return MENU

    response = "📋 <b>Suas Ofertas Ativas:</b>\n\n"
    keyboard = []
    for order in orders:
        ord_type = "COMPRA" if order.order_type == "BUY" else "VENDA"
        qty_str = f"{order.quantity:,}".replace(",", ".")
        price_str = f"R$ {order.price_per_thousand:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        response += (
            f"🔹 <b>#{order.id}</b> | {ord_type} | <b>{order.program.name}</b>\n"
            f"   Quantidade: {qty_str} milhas\n"
            f"   Valor: {price_str} o milheiro\n\n"
        )
        keyboard.append([InlineKeyboardButton(f"🗑️ Excluir #{order.id}", callback_data=f"cancel_ad_{order.id}")])
    
    keyboard.append([InlineKeyboardButton("🗑️ Excluir Todos", callback_data="cancel_ad_all")])
    keyboard.append([InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="back_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='HTML')
        
    db.close()
    return MY_ADS

async def handle_cancel_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_menu":
        return await start(update, context)

    try:
        user_data = update.effective_user
        db = SessionLocal()
        user = db.query(User).filter(User.telegram_id == user_data.id).first()
        
        target = query.data.split("_")[2]
        if target == "all":
            orders = db.query(Order).filter(Order.user_id == user.id, Order.status == OrderStatus.PENDING).all()
            for order in orders:
                order.status = OrderStatus.CANCELLED
            db.commit()
            await query.message.reply_text("Todos os anúncios foram cancelados com sucesso.")
        else:
            order_id = int(target)
            order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
            if order:
                order.status = OrderStatus.CANCELLED
                db.commit()
                await query.message.reply_text(f"Anúncio #{order_id} cancelado com sucesso.")
        
        db.close()
    except Exception as e:
        await query.message.reply_text("Seleção inválida.")

    return await list_my_ads(update, context)

def format_price_br(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

def build_order_proposal_markup(order: Order):
    if order.status != OrderStatus.PENDING:
        return None
    label = "Vender para esta oferta" if order.order_type == "BUY" else "Comprar desta oferta"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"proposal_{order.id}")]])

async def proposal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[1])

    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()
    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()

    if not order or order.status != OrderStatus.PENDING:
        db.close()
        await query.answer("Esta oferta não está mais disponível.", show_alert=True)
        return ConversationHandler.END

    if not user:
        db.close()
        await query.answer("Usuário não encontrado.", show_alert=True)
        return ConversationHandler.END

    if order.user_id == user.id:
        db.close()
        await query.answer("Você não pode enviar proposta para sua própria oferta.", show_alert=True)
        return ConversationHandler.END

    context.user_data["proposal_order_id"] = order.id
    context.user_data["proposal_role"] = "seller" if order.order_type == "BUY" else "buyer"

    qty_str = f"{order.quantity:,}".replace(",", ".")
    text = (
        f"Você está prestes a enviar uma proposta para a oferta #{order.id}.\n"
        f"Programa: {order.program.name}\n"
        f"Quantidade: {qty_str} milhas\n"
        f"Preço atual: {format_price_br(order.price_per_thousand)} por milheiro\n\n"
        "Deseja manter este valor ou fazer uma contraproposta?"
    )
    db.close()
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Manter o preço", callback_data="proposal_keep")],
        [InlineKeyboardButton("Fazer contraproposta", callback_data="proposal_counter")],
        [InlineKeyboardButton("Cancelar", callback_data="proposal_cancel")],
    ])

    try:
        await context.bot.send_message(chat_id=update.effective_user.id, text=text, reply_markup=reply_markup)
        await query.answer("Verifique as mensagens privadas do bot.", show_alert=True)
    except Exception:
        await query.answer("Abra uma conversa privada com o bot primeiro.", show_alert=True)

async def proposal_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.replace("proposal_", "")
    order_id = context.user_data.get("proposal_order_id")

    if choice == "cancel":
        await query.edit_message_text("Solicitação de proposta cancelada.")
        return ConversationHandler.END

    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order or order.status != OrderStatus.PENDING:
        db.close()
        await query.edit_message_text("Esta oferta não está mais disponível.")
        return ConversationHandler.END

    if choice == "keep":
        context.user_data["proposal_price"] = order.price_per_thousand
        await query.edit_message_text(
            f"Enviar proposta de {format_price_br(order.price_per_thousand)} para a oferta #{order.id}?\n"
            "Se sim, confirme abaixo.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Enviar proposta", callback_data="proposal_send")],
                [InlineKeyboardButton("Cancelar", callback_data="proposal_cancel")],
            ])
        )
        db.close()
        return PROPOSE_CONFIRM_SEND

    db.close()
    await query.edit_message_text("Qual valor por milheiro você deseja propor? Digite apenas números.")
    return PROPOSE_PRICE

async def proposal_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", "."))
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Valor inválido. Digite apenas números, sem símbolos.")
        return PROPOSE_PRICE

    order_id = context.user_data.get("proposal_order_id")
    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order or order.status != OrderStatus.PENDING:
        db.close()
        await update.message.reply_text("Esta oferta não está mais disponível.")
        return ConversationHandler.END

    context.user_data["proposal_price"] = price
    await update.message.reply_text(
        f"Enviar proposta de {format_price_br(price)} para a oferta #{order.id}?\n"
        "Se sim, confirme abaixo.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Enviar proposta", callback_data="proposal_send")],
            [InlineKeyboardButton("Cancelar", callback_data="proposal_cancel")],
        ])
    )
    db.close()
    return PROPOSE_CONFIRM_SEND

async def send_proposal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "proposal_cancel":
        await query.edit_message_text("Solicitação de proposta cancelada.")
        return ConversationHandler.END

    order_id = context.user_data.get("proposal_order_id")
    price = context.user_data.get("proposal_price")

    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()
    sender = db.query(User).filter(User.telegram_id == update.effective_user.id).first()

    if not order or order.status != OrderStatus.PENDING:
        db.close()
        await query.edit_message_text("Esta oferta não está mais disponível.")
        return ConversationHandler.END

    if not sender:
        db.close()
        await query.edit_message_text("Usuário não encontrado.")
        return ConversationHandler.END

    proposal = OfferProposal(
        order_id=order.id,
        sender_id=sender.id,
        recipient_id=order.user_id,
        price_per_thousand=price,
        status=ProposalStatus.PENDING,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)

    proposer_rating = "N/A" if sender.total_reviews == 0 else f"{sender.rating:.1f} ({sender.total_reviews} avaliações)"
    verification_icon = "✅" if sender.is_verified else "🛑"
    
    proposer_info = (
        f"⭐️ Avaliação: {proposer_rating}\n"
        f"{verification_icon} Verificado: {'Sim' if sender.is_verified else 'Não'}"
    )
    
    qty_str = f"{order.quantity:,}".replace(",", ".")
    recipient_text = (
        f"💰 Novo interesse na sua oferta #{order.id}.\n\n"
        f"Programa: {order.program.name}\n"
        f"Quantidade: {qty_str} milhas\n"
        f"Valor da proposta: {format_price_br(price)} por milheiro\n\n"
        f"{proposer_info}\n\n"
        "Se quiser aceitar esta proposta, clique em Aceitar proposta."
    )
    
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    profile_url = f"{base_url}/profile/{sender.id}"
    
    recipient_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Ver Perfil", web_app=WebAppInfo(url=profile_url))],
        [InlineKeyboardButton("🟢 Aceitar proposta", callback_data=f"proposal_accept_{proposal.id}")],
        [InlineKeyboardButton("🔴 Recusar proposta", callback_data=f"proposal_reject_{proposal.id}")],
    ])

    try:
        await context.bot.send_message(chat_id=order.user.telegram_id, text=recipient_text, reply_markup=recipient_markup, parse_mode='HTML')
        await query.edit_message_text("Sua proposta foi enviada. Aguarde a resposta do dono da oferta.")
    except Exception:
        await query.edit_message_text("Não foi possível enviar a proposta. Abra o bot no seu privado e tente novamente.")

    db.close()
    return ConversationHandler.END

async def accept_proposal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    proposal_id = int(query.data.split("_")[2])

    db = SessionLocal()
    proposal = db.query(OfferProposal).filter(OfferProposal.id == proposal_id).first()
    if not proposal or proposal.status != ProposalStatus.PENDING:
        db.close()
        await query.edit_message_text("Esta proposta não está mais disponível.")
        return ConversationHandler.END

    order = proposal.order
    if order.status != OrderStatus.PENDING:
        db.close()
        await query.edit_message_text("Esta oferta já está em negociação.")
        return ConversationHandler.END

    order.status = OrderStatus.MATCHED
    order.accepted_proposal_id = proposal.id
    proposal.status = ProposalStatus.ACCEPTED

    pending_others = db.query(OfferProposal).filter(
        OfferProposal.order_id == order.id,
        OfferProposal.status == ProposalStatus.PENDING,
        OfferProposal.id != proposal.id
    ).all()
    for other in pending_others:
        other.status = ProposalStatus.REJECTED

    db.commit()

    sender = proposal.sender
    owner = proposal.recipient
    other_username = f"@{sender.username}" if sender.username else f"[{sender.full_name}](tg://user?id={sender.telegram_id})"
    owner_username = f"@{owner.username}" if owner.username else f"[{owner.full_name}](tg://user?id={owner.telegram_id})"
    action_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Concluir negociação", callback_data=f"conclude_negotiation_{order.id}")],
        [InlineKeyboardButton("Cancelar negociação", callback_data=f"cancel_negotiation_{order.id}")],
    ])

    qty_str = f"{order.quantity:,}".replace(",", ".")
    await query.edit_message_text(
        f"📌 Você escolheu {other_username} para a oferta #{order.id}.\n"
        f"Quantidade: {qty_str} milhas\n"
        f"Valor aceito: {format_price_br(proposal.price_per_thousand)} por milheiro\n\n"
        "A partir de agora, converse no privado e finalize a emissão.",
        reply_markup=action_markup,
        parse_mode='Markdown'
    )

    try:
        await context.bot.send_message(
            chat_id=sender.telegram_id,
            text=(
                f"✅ Sua proposta foi aceita!\n"
                f"Oferta #{order.id}\n"
                f"Programa: {order.program.name}\n"
                f"Quantidade: {qty_str} milhas\n"
                f"Valor: {format_price_br(proposal.price_per_thousand)} por milheiro\n\n"
                f"Entre em contato com {owner_username} no Telegram para finalizar."
            ),
            reply_markup=action_markup,
            parse_mode='Markdown'
        )
    except Exception:
        pass

    db.close()
    return ConversationHandler.END

async def reject_proposal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    proposal_id = int(query.data.split("_")[2])

    db = SessionLocal()
    proposal = db.query(OfferProposal).filter(OfferProposal.id == proposal_id).first()
    if not proposal or proposal.status != ProposalStatus.PENDING:
        db.close()
        await query.edit_message_text("Esta proposta não está mais disponível.")
        return ConversationHandler.END

    proposal.status = ProposalStatus.REJECTED
    db.commit()

    await query.edit_message_text("Proposta rejeitada.")
    try:
        await context.bot.send_message(chat_id=proposal.sender.telegram_id, text=f"Sua proposta para a oferta #{proposal.order.id} foi recusada.")
    except Exception:
        pass

    db.close()
    return ConversationHandler.END

async def cancel_negotiation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[2])

    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.status != OrderStatus.MATCHED or not order.accepted_proposal_id:
        db.close()
        await query.edit_message_text("Não há negociação ativa para cancelar.")
        return ConversationHandler.END

    proposal = db.query(OfferProposal).filter(OfferProposal.id == order.accepted_proposal_id).first()
    if not proposal:
        db.close()
        await query.edit_message_text("Negociação inválida.")
        return ConversationHandler.END

    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    if not user or user.id not in (proposal.sender_id, proposal.recipient_id):
        db.close()
        await query.edit_message_text("Você não participa desta negociação.")
        return ConversationHandler.END

    proposal.status = ProposalStatus.CANCELLED
    order.status = OrderStatus.PENDING
    order.accepted_proposal_id = None
    db.commit()

    message = f"❌ A negociação da oferta #{order.id} foi cancelada. A oferta está novamente aberta para novas propostas."
    for participant in [proposal.sender, proposal.recipient]:
        try:
            await context.bot.send_message(chat_id=participant.telegram_id, text=message)
        except Exception:
            pass

    await query.edit_message_text("Negociação cancelada. A oferta está novamente aberta.")
    db.close()
    return ConversationHandler.END

async def conclude_negotiation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[2])

    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.status != OrderStatus.MATCHED or not order.accepted_proposal_id:
        db.close()
        await query.edit_message_text("Não há negociação ativa para concluir.")
        return ConversationHandler.END

    proposal = db.query(OfferProposal).filter(OfferProposal.id == order.accepted_proposal_id).first()
    if not proposal:
        db.close()
        await query.edit_message_text("Negociação inválida.")
        return ConversationHandler.END

    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    if not user or user.id not in (proposal.sender_id, proposal.recipient_id):
        db.close()
        await query.edit_message_text("Você não participa desta negociação.")
        return ConversationHandler.END

    order.status = OrderStatus.COMPLETED
    db.commit()

    for participant in [proposal.sender, proposal.recipient]:
        counterpart = proposal.sender if participant.id == proposal.recipient_id else proposal.recipient

        notify_text = (
            f"✅ A negociação da oferta #{order.id} foi marcada como concluída.\n"
            "Você pode agora avaliar a contraparte."
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Avaliar contraparte ⭐", callback_data=f"rate_user_{order.id}_{counterpart.id}")]
        ])

        try:
            await context.bot.send_message(chat_id=participant.telegram_id, text=notify_text, reply_markup=buttons)
        except Exception:
            pass

    await query.edit_message_text("Operação concluída. Os envolvidos foram notificados para avaliação.")
    db.close()
    return ConversationHandler.END

async def rate_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    order_id = parts[2]
    target_id = int(parts[3])

    db = SessionLocal()
    order = db.query(Order).filter(Order.id == int(order_id)).first()
    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    target = db.query(User).filter(User.id == target_id).first()
    db.close()

    if not order or order.status != OrderStatus.COMPLETED or not user or not target:
        await query.edit_message_text("Avaliação não disponível para esta negociação.")
        return ConversationHandler.END

    context.user_data["feedback_order_id"] = int(order_id)
    context.user_data["feedback_target_id"] = target_id
    
    keyboard = [
        [
            InlineKeyboardButton("⭐ 1", callback_data="star_1"),
            InlineKeyboardButton("⭐ 2", callback_data="star_2"),
            InlineKeyboardButton("⭐ 3", callback_data="star_3"),
            InlineKeyboardButton("⭐ 4", callback_data="star_4"),
            InlineKeyboardButton("⭐ 5", callback_data="star_5")
        ]
    ]
    await query.edit_message_text(
        f"Como você avalia a sua experiência com a contraparte?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return FEEDBACK_STAR

async def feedback_star_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    stars = int(query.data.split("_")[1])
    context.user_data["feedback_stars"] = stars
    
    await query.edit_message_text(
        f"Você deu {stars} estrela(s)!\n"
        "Agora, por favor, envie um breve comentário sobre a negociação (ou digite algo simples para finalizar)."
    )
    return FEEDBACK_COMMENT

async def feedback_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text.strip()
    order_id = context.user_data.get("feedback_order_id")
    target_id = context.user_data.get("feedback_target_id")
    stars = context.user_data.get("feedback_stars", 5)

    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    target = db.query(User).filter(User.id == target_id).first()
    order = db.query(Order).filter(Order.id == order_id).first()
    if not user or not target or not order:
        db.close()
        await update.message.reply_text("Não foi possível registrar o feedback.")
        return ConversationHandler.END

    rating = stars
    feedback = Feedback(
        order_id=order.id,
        from_user_id=user.id,
        to_user_id=target.id,
        rating=rating,
        comment=comment,
    )
    db.add(feedback)
    target.total_reviews += 1
    target.rating = (target.rating * (target.total_reviews - 1) + rating) / target.total_reviews
    db.commit()
    db.close()

    await update.message.reply_text("Obrigado pelo feedback!", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def buy_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["order_type"] = "BUY"
    await query.edit_message_text("Quantas milhas você deseja comprar?")
    return BUY_QUANTITY

    await query.answer()
    context.user_data["order_type"] = "BUY"
    await query.edit_message_text("Quantas milhas você deseja comprar?")
    return BUY_QUANTITY

async def sell_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["order_type"] = "SELL"
    await query.edit_message_text("Quantas milhas você deseja vender?")
    return BUY_QUANTITY

async def get_buy_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.replace(".", "").replace(",", ""))
        context.user_data["quantity"] = qty
        
        db = SessionLocal()
        programs = db.query(Program).filter(Program.is_active == True).order_by(Program.name).all()
        db.close()
        
        if not programs:
            await update.message.reply_text("Nenhum programa ativo disponível no momento. Contate o suporte.")
            return ConversationHandler.END
            
        keyboard = []
        for i in range(0, len(programs), 2):
            row = [InlineKeyboardButton(p.name, callback_data=f"prog_{p.name}") for p in programs[i:i+2]]
            keyboard.append(row)
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Para qual programa?", reply_markup=reply_markup)
        
        return BUY_PROGRAM
    except ValueError:
        await update.message.reply_text("Por favor, digite apenas números.")
        return BUY_QUANTITY

async def get_buy_program(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    program_name = query.data.replace("prog_", "")
    context.user_data["program"] = program_name

    await query.edit_message_text("Para quantos passageiros será a emissão?")
    return BUY_PASSENGERS

async def get_passengers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["passengers"] = update.message.text
    keyboard = [[InlineKeyboardButton("Sim", callback_data="v_low"), InlineKeyboardButton("Não", callback_data="v_high")]]
    await update.message.reply_text("A passagem que você quer emitir é para ser usada dentro dos próximos 7 dias?", reply_markup=InlineKeyboardMarkup(keyboard))
    return BUY_DEADLINE

async def get_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    prazos = {
        "v_low": "Menos de 7 dias",
        "v_high": "Mais de 7 dias"
    }
    
    context.user_data["deadline"] = prazos.get(query.data, query.data)
    
    await query.edit_message_text("Qual o valor do milheiro? (Ex: 16,50)")
    return BUY_PRICE

async def get_buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", "."))
        context.user_data["price"] = price
        
        qty = context.user_data["quantity"]
        total = (qty / 1000) * price
        
        tipo_acao = "comprando" if context.user_data['order_type'] == "BUY" else "vendendo"
        
        summary = (
            f"Confirme sua oferta:\n\n"
            f"Você está {tipo_acao} **{qty:,} milhas** do programa **{context.user_data['program']}** "
            f"por **R$ {price:,.2f}** o milheiro. Valor total **R$ {total:,.2f}**"
        ).replace(",", "X").replace(".", ",").replace("X", ".")

        keyboard = [[InlineKeyboardButton("Confirmar ✅", callback_data="confirm"), InlineKeyboardButton("Cancelar ❌", callback_data="cancel")]]
        await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return CONFIRM_BUY
    except ValueError:
        await update.message.reply_text("Valor inválido.")
        return BUY_PRICE

async def finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm":
        db = SessionLocal()
        user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
        
        program_name = context.user_data["program"]
        program = db.query(Program).filter(Program.name == program_name).first()
        
        if not program:
            program = Program(name=program_name)
            db.add(program)
            db.flush()

        qty = context.user_data["quantity"]
        price_k = context.user_data["price"]
        total_val = (qty / 1000) * price_k
        
        new_order = Order(
            user_id=user.id,
            program_id=program.id,
            order_type=context.user_data["order_type"],
            quantity=qty,
            price_per_thousand=price_k,
            total_value=total_val,
            status=OrderStatus.PENDING
        )
        db.add(new_order)
        db.commit()

        def fmt_money(v):
            return f"{v:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

        f_price = f"R$ {fmt_money(price_k)}"
        f_total = f"R$ {fmt_money(total_val)}"
        f_qty = f"{qty:,}".replace(",", ".")
        
        action = "comprar" if new_order.order_type == "BUY" else "vender"
        payment_action = "pagar" if new_order.order_type == "BUY" else "receber"
        rating = f"{user.rating} ({user.total_reviews})" if user.total_reviews > 0 else "N/A"
        verification_icon = "✅" if user.is_verified else "🛑"
        
        announcement = (
            f"Quero {action} <b>{f_qty}</b> milhas do programa <b>{program.name}</b> "
            f"com emissão para <b>{context.user_data['passengers']} PASSAGEIROS</b>. "
            f"Quero {payment_action} <b>{f_price}</b> no milheiro ({f_total} + taxas no total)\n\n"
            f"DETALHES DA OFERTA\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 Oferta: #{new_order.id}\n"
            f"✈️ Programa: {program.name}\n"
            f"💎 Quantidade: {f_qty}\n"
            f"💰 Valor do Milheiro: {f_price}\n"
            f"💵 Valor Total: {f_total}\n"
            f"📅 Emissão: {context.user_data['deadline']}\n"
            f"DETALHES DO USUÁRIO\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⭐ Avaliação: {rating}\n"
            f"{verification_icon} Verificado: {'Sim' if user.is_verified else 'Não'}\n"
        )

        setting_key = "buy_channel_id" if new_order.order_type == "BUY" else "sell_channel_id"
        channel_id = get_setting(setting_key, "")

        if channel_id:
            try:
                btn_text = "VENDER PARA ESTA OFERTA" if new_order.order_type == "BUY" else "COMPRAR DESTA OFERTA"
                trade_keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(btn_text, url=f"https://t.me/{context.bot.username}?start=proposal_{new_order.id}")]]
                )
                if program.banner_url:
                    await context.bot.send_photo(chat_id=channel_id, photo=program.banner_url, caption=announcement, parse_mode='HTML', reply_markup=trade_keyboard)
                else:
                    await context.bot.send_message(chat_id=channel_id, text=announcement, parse_mode='HTML', reply_markup=trade_keyboard)
            except Exception as e:
                print(f"Erro ao postar: {e}")

        db.close()
        
        await query.edit_message_text(f"✅ Anúncio <b>#{new_order.id}</b> publicado com sucesso!", parse_mode='HTML')
        
    else:
        await query.edit_message_text("❌ Operação cancelada.")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Aborted.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    init_db()
    db = SessionLocal()
    bootstrap_data(db)
    db.close()
    
    application = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, start),
            CallbackQueryHandler(buy_request, pattern="^buy$"),
            CallbackQueryHandler(sell_request, pattern="^sell$"),
            CallbackQueryHandler(list_my_ads, pattern="^my_ads$"),
            CallbackQueryHandler(proposal_start, pattern=r"^proposal_\d+$"),
        ],
        states={
            MENU: [
                CallbackQueryHandler(buy_request, pattern="^buy$"),
                CallbackQueryHandler(sell_request, pattern="^sell$"),
                CallbackQueryHandler(list_my_ads, pattern="^my_ads$"),
                CallbackQueryHandler(start, pattern="^support$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, start),
            ],
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reg_name)],
            REG_CPF: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reg_cpf)],
            REG_BIRTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reg_birth)],
            BUY_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_buy_quantity)],
            BUY_PROGRAM: [CallbackQueryHandler(get_buy_program, pattern=r"^prog_")],
            BUY_PASSENGERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_passengers)],
            BUY_DEADLINE: [CallbackQueryHandler(get_deadline, pattern="^(v_low|v_high)$")], 
            BUY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_buy_price)],
            CONFIRM_BUY: [CallbackQueryHandler(finish_order, pattern="^(confirm|cancel)$")],
            MY_ADS: [CallbackQueryHandler(handle_cancel_ad, pattern="^(cancel_ad_|back_menu)")],
            PROPOSE_CONFIRM: [CallbackQueryHandler(proposal_choice, pattern=r"^proposal_(keep|counter|cancel)$")],
            PROPOSE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, proposal_price)],
            PROPOSE_CONFIRM_SEND: [CallbackQueryHandler(send_proposal, pattern=r"^proposal_(send|cancel)$")],
            FEEDBACK_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_comment)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(accept_proposal, pattern=r"^proposal_accept_\d+$"))
    application.add_handler(CallbackQueryHandler(reject_proposal, pattern=r"^proposal_reject_\d+$"))
    application.add_handler(CallbackQueryHandler(cancel_negotiation, pattern=r"^cancel_negotiation_\d+$"))
    application.add_handler(CallbackQueryHandler(conclude_negotiation, pattern=r"^conclude_negotiation_\d+$"))
    application.add_handler(CallbackQueryHandler(rate_user_callback, pattern=r"^rate_user_\d+_\d+$"))
    
    print("FlyTrade Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
