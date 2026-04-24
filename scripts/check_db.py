import json, re, sys
sys.path.insert(0, "/app")
from app.database import SessionLocal
from app.models import SiteSettings, HomepageContent

db = SessionLocal()
s = db.query(SiteSettings).first()
if s:
    print("logo_url:", s.logo_url)
    print("logo_white_url:", s.logo_white_url)
    print("favicon_url:", s.favicon_url)
else:
    print("site_settings BOS")

hps = db.query(HomepageContent).all()
print(f"\nhomepage_contents: {len(hps)} kayit")
for hp in hps:
    d = hp.data if isinstance(hp.data, str) else json.dumps(hp.data)
    urls = re.findall(r"/static/upload/images/[^\"'\s]+", d)
    if urls:
        print(f"  [{hp.lang}]: {urls[:6]}")
    else:
        print(f"  [{hp.lang}]: gorsel URL yok")
db.close()
