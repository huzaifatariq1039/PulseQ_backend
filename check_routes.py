
from main import app

routes = [(r.path, r.methods) for r in app.routes if 'doctor' in r.path.lower() or 'department' in r.path.lower()]

print("\n" + "="*80)
print("DOCTOR & DEPARTMENT ROUTES")
print("="*80 + "\n")

for path, methods in sorted(routes):
    method_list = list(methods) if methods else ['ANY']
    for method in method_list:
        print(f"{method:8s} {path}")

print("\n" + "="*80)
print(f"Total: {len(routes)} routes")
print("="*80 + "\n")
