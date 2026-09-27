# app/seed/seed_exhibitor_whitelist.py
# Seed allowed exhibitor emails.

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.exhibitor_whitelist import ExhibitorWhitelist

EXHIBITOR_EMAILS = [
    "exhibitor1@example.com",
    "exhibitor2@example.com",
    "exhibitor3@example.com",
    "techcorp@company.com",
    "innovations@startup.io",
    "booth@enterprise.com",
    "exhibitor4@example.com",
    "exhibitor5@example.com",
    "exhibitor6@example.com",
    "exhibitor7@example.com",
    "exhibitor8@example.com",
    "exhibitor9@example.com",
    "exhibitor10@example.com",
    "sales@techventures.io",
    "info@greektech.gr",
    "contact@digitalwave.gr",
    "booth@nexuslab.io",
    "exhibit@futureforge.com",
    "press@alphasoft.gr",
    "demo@betaworks.io",
    "showcase@gammainc.com",
    "stand@deltagroup.gr",
    "info@epsilontech.eu",
    "exhibit@zetadigital.io",
    "hello@etainnovate.com",
    "contact@thetaventures.gr",
    "booth@iotanetworks.io",
    "sales@kappasystems.com",
    "info@lambdacloud.gr",
    "demo@musolutions.io",
    "exhibit@nusoftware.com",
    "stand@xisecurity.eu",
    "contact@omicronapps.gr",
    "info@piplatforms.io",
    "sales@rhosystems.com",
    "booth@sigmadigital.gr",
    "demo@tautech.io",
    "exhibit@upsilonai.com",
    "hello@phidata.gr",
    "info@chirobots.io",
    "contact@psianalytics.com",
    "stand@omegacloud.gr",
    "sales@horizontech.eu",
    "booth@meridiansoft.io",
    "demo@zenithinc.com",
    "exhibit@apexventures.gr",
    "info@vertexlabs.io",
    "contact@novadigital.eu",
    "showcase@pulseworks.gr",
    "sales@orbittech.io",
    "booth@quantumsys.com",
    "demo@nexagroup.gr",
    "exhibit@vortexai.io",
    "info@synapsesolutions.com",
    "contact@heliossoftware.gr",
    "stand@astroinnovate.io",
]


def main():
    db: Session = SessionLocal()
    try:
        created = 0
        for email in EXHIBITOR_EMAILS:
            email_lower = email.lower()
            exists = db.query(ExhibitorWhitelist).filter(
                ExhibitorWhitelist.email == email_lower
            ).first()
            if not exists:
                db.add(ExhibitorWhitelist(email=email_lower))
                created += 1

        db.commit()
        print(f"Seed exhibitor whitelist done. Created {created} entries.")
    finally:
        db.close()


run = main

if __name__ == "__main__":
    run()
