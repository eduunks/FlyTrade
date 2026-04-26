import re

def is_valid_cpf(cpf: str) -> bool:
    cpf = re.sub(r'\D', '', cpf)

    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False

    for i in range(9, 11):
        value = sum((int(cpf[num]) * ((i + 1) - num) for num in range(i)))
        check = ((value * 10) % 11) % 10
        if check != int(cpf[i]):
            return False
    return True