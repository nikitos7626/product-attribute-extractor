import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.vm_exec import exec_remote

code = """
import urllib.request, json
phone_card = {
    'raw_text': 'Смартфон Apple iPhone 16 Pro 128 ГБ в черном цвете. Смартфон оснащен процессором Apple A18 Pro с частотой 3890 МГц и 6 ядрами. Конфигурация памяти составляет 128 ГБ. Экран имеет диагональ 6.3 дюйма и разрешение 2622x1206 пикселей OLED 120 Гц. Корпус смартфона выполнен из титана. В комплекте с смартфоном идут кабель USB C, документация и наушники.'
}
req = urllib.request.Request(
    'http://127.0.0.1:8000/api/extract',
    data=json.dumps(phone_card).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode('utf-8'))
    print(f"CATEGORY: {res.get('category')}")
    print(f"OVERALL CONFIDENCE: {res.get('overall_confidence')}")
    print("PREDICTIONS:")
    for p in res.get('predictions', []):
        print(f"  • {p['attribute']}: {p['value']} (src={p['source']})")

"""

if __name__ == "__main__":
    asyncio.run(exec_remote(code))

