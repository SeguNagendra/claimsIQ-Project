from app.models import Audit
def add_audit(db, actor_id, action, resource): db.add(Audit(actor_id=actor_id,action=action,resource=resource))
