from careiq.audit import run_consistency_audit
from careiq.config import AUDIT_PATH, DB_PATH

print(run_consistency_audit(DB_PATH, AUDIT_PATH))
