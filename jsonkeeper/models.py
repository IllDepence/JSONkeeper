from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()


class JSON_document(db.Model):
    id = db.Column(db.String(255), primary_key=True)
    access_token = db.Column(db.String(255))
    json_string = db.Column(db.UnicodeText())
    created_at = db.Column(db.DateTime(timezone=True),
                           server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True),
                           onupdate=func.now())
