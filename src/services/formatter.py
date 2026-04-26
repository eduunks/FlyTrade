from src.services.config_service import get_setting

def format_currency_custom(value: float) -> str:
    symbol = get_setting("currency_symbol", "$")
    position = get_setting("currency_position", "before")
    thousand_sep = get_setting("thousand_separator", ",")
    decimal_sep = get_setting("decimal_separator", ".")
    
    formatted_number = "{:,.2f}".format(value)
    
    if thousand_sep == ".":
        main_part, dec_part = formatted_number.split(".")
        main_part = main_part.replace(",", ".")
        formatted_number = f"{main_part}{decimal_sep}{dec_part}"
    elif decimal_sep == ",":
        formatted_number = formatted_number.replace(".", "TEMP").replace(",", thousand_sep).replace("TEMP", ",")

    if position == "before":
        return f"{symbol}{formatted_number}"
    return f"{formatted_number}{symbol}"