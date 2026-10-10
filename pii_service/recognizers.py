"""Named, trusted checksum validators; regexes live in YAML."""
import re


def validate_tw_id(text: str) -> bool:
    text = text.strip().upper()
    if not re.fullmatch(r'[A-Z][12][0-9]{8}', text):
        return False
    codes = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ', [10,11,12,13,14,15,16,17,34,18,19,20,21,22,35,23,24,25,26,27,28,29,32,30,31,33]))
    a, b = divmod(codes[text[0]], 10)
    return sum(d*w for d,w in zip([a,b] + [int(c) for c in text[1:]], [1,9,8,7,6,5,4,3,2,1,1])) % 10 == 0


def validate_tw_tax_id(text: str) -> bool:
    if not re.fullmatch(r'[0-9]{8}', text):
        return False
    products = [int(c)*w for c,w in zip(text, [1,2,1,2,1,2,4,1])]
    total = sum(n//10+n%10 for n in products)
    return total % 10 == 0 or (text[6] == '7' and (total-1) % 10 == 0)


VALIDATORS = {'tw_id': validate_tw_id, 'tw_tax_id': validate_tw_tax_id}
