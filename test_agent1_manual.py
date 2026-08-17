from dotenv import load_dotenv
load_dotenv()

from agent1_classification import classify
import json

result = classify("what's the procedure", "customer", "public")
print(json.dumps(result, indent=2))