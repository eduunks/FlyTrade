import os
import uvicorn
import multiprocessing
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import BotCommand

from src.database.connection import SessionLocal, init_db, bootstrap_data
from src.web.main import app
from src.bot.main import (
    start, buy_request, sell_request, list_my_ads, 
    get_buy_quantity, get_buy_program, get_passengers, get_deadline, get_buy_price, 
    finish_order, handle_cancel_ad, cancel, config_command,
    get_reg_name, get_reg_cpf, get_reg_birth,
    proposal_start, proposal_choice, proposal_price, send_proposal, 
    accept_proposal, reject_proposal, cancel_negotiation, conclude_negotiation, rate_user_callback, feedback_star_callback, feedback_comment,
    MENU, BUY_QUANTITY, BUY_PROGRAM, BUY_PASSENGERS, BUY_DEADLINE, BUY_PRICE, CONFIRM_BUY, MY_ADS,
    REG_NAME, REG_CPF, REG_BIRTH,
    PROPOSE_CONFIRM, PROPOSE_PRICE, PROPOSE_CONFIRM_SEND, FEEDBACK_STAR, FEEDBACK_COMMENT
)

load_dotenv()

async def set_commands(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Abrir o menu principal")
    ])

def run_bot():
    application = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).post_init(set_commands).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, start),
            CallbackQueryHandler(buy_request, pattern="^buy$"),
            CallbackQueryHandler(sell_request, pattern="^sell$"),
            CallbackQueryHandler(list_my_ads, pattern="^my_ads$"),
            CallbackQueryHandler(start, pattern="^support$"),
            CallbackQueryHandler(proposal_choice, pattern=r"^proposal_(keep|counter|cancel)$"),
            CallbackQueryHandler(rate_user_callback, pattern=r"^rate_user_\d+_\d+$"),
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
            BUY_DEADLINE: [CallbackQueryHandler(get_deadline)],
            BUY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_buy_price)],
            CONFIRM_BUY: [CallbackQueryHandler(finish_order, pattern="^(confirm|cancel)$")],
            MY_ADS: [CallbackQueryHandler(handle_cancel_ad, pattern="^(cancel_ad_|back_menu)")],
            PROPOSE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, proposal_price)],
            PROPOSE_CONFIRM_SEND: [CallbackQueryHandler(send_proposal, pattern=r"^proposal_(send|cancel)$")],
            FEEDBACK_STAR: [CallbackQueryHandler(feedback_star_callback, pattern=r"^star_")],
            FEEDBACK_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_comment)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        per_message=False
    )

    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CallbackQueryHandler(proposal_start, pattern=r"^proposal_\d+$"))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(accept_proposal, pattern=r"^proposal_accept_\d+$"))
    application.add_handler(CallbackQueryHandler(reject_proposal, pattern=r"^proposal_reject_\d+$"))
    application.add_handler(CallbackQueryHandler(cancel_negotiation, pattern=r"^cancel_negotiation_\d+$"))
    application.add_handler(CallbackQueryHandler(conclude_negotiation, pattern=r"^conclude_negotiation_\d+$"))
    
    print("Bot Rodando...")
    application.run_polling()

def run_web():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")

if __name__ == "__main__":
    init_db()
    process_web = multiprocessing.Process(target=run_web)
    process_bot = multiprocessing.Process(target=run_bot)
    process_web.start()
    process_bot.start()
    process_web.join()
    process_bot.join()