import time
import uuid

def generate_payment_id() -> str:
    return f"pay_{int(time.time())}_{uuid.uuid4().hex[:8]}"