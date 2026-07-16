# ═══════════════════════════════════════════════════════
#  EDUTRACK — Backend complet en 1 fichier
#  FastAPI + SQLite
#  Lance avec : python app.py
# ═══════════════════════════════════════════════════════

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import hashlib, secrets, enum, uvicorn

# ── BASE DE DONNÉES ────────────────────────────────────
engine       = create_engine("sqlite:///./edutrack.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── MODÈLES (TABLES) ───────────────────────────────────
class TypeEnum(str, enum.Enum):
    absent = "absent"
    retard = "retard"

class Professeur(Base):
    __tablename__ = "professeurs"
    id           = Column(Integer, primary_key=True, index=True)
    nom          = Column(String, nullable=False)
    prenom       = Column(String, nullable=False)
    email        = Column(String, unique=True, index=True, nullable=False)
    mot_de_passe = Column(String, nullable=False)
    matiere      = Column(String, nullable=False)
    actif        = Column(Boolean, default=True)
    cree_le      = Column(DateTime(timezone=True), server_default=func.now())

class Eleve(Base):
    __tablename__ = "eleves"
    id           = Column(Integer, primary_key=True, index=True)
    nom          = Column(String, nullable=False)
    prenom       = Column(String, nullable=False)
    classe       = Column(String, nullable=False)
    tel_parent   = Column(String, nullable=True)
    actif        = Column(Boolean, default=True)
    cree_le      = Column(DateTime(timezone=True), server_default=func.now())

class Absence(Base):
    __tablename__ = "absences"
    id            = Column(Integer, primary_key=True, index=True)
    eleve_id      = Column(Integer, nullable=False)
    professeur_id = Column(Integer, nullable=False)
    type          = Column(SAEnum(TypeEnum), nullable=False)
    matiere       = Column(String, nullable=False)
    classe        = Column(String, nullable=False)
    motif         = Column(String, nullable=True)
    heure         = Column(String, nullable=False)
    date          = Column(String, nullable=False)
    valide        = Column(Boolean, default=True)
    cree_le       = Column(DateTime(timezone=True), server_default=func.now())

# Crée les tables
Base.metadata.create_all(bind=engine)

# ── SCHEMAS (VALIDATION) ───────────────────────────────
class ProfesseurCreate(BaseModel):
    nom: str
    prenom: str
    email: str
    mot_de_passe: str
    matiere: str

class ProfesseurOut(BaseModel):
    id: int
    nom: str
    prenom: str
    email: str
    matiere: str
    class Config:
        from_attributes = True

class LoginIn(BaseModel):
    email: str
    mot_de_passe: str

class EleveCreate(BaseModel):
    nom: str
    prenom: str
    classe: str
    tel_parent: Optional[str] = None

class EleveOut(BaseModel):
    id: int
    nom: str
    prenom: str
    classe: str
    tel_parent: Optional[str]
    nb_absences: int = 0
    nb_retards: int = 0
    class Config:
        from_attributes = True

class AbsenceCreate(BaseModel):
    eleve_id: int
    professeur_id: int
    type: TypeEnum
    matiere: str
    classe: str
    motif: Optional[str] = None
    heure: str
    date: str

class AbsenceOut(BaseModel):
    id: int
    eleve_id: int
    professeur_id: int
    type: str
    matiere: str
    classe: str
    motif: Optional[str]
    heure: str
    date: str
    valide: bool
    eleve_nom: Optional[str] = None
    class Config:
        from_attributes = True

# ── APP ────────────────────────────────────────────────
app = FastAPI(
    title="EduTrack API",
    description="Gestion des absences et retards scolaires",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── UTILITAIRES ────────────────────────────────────────
def hasher(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def compter(db: Session, eleve_id: int, type: str) -> int:
    return db.query(Absence).filter(
        Absence.eleve_id == eleve_id,
        Absence.type == type
    ).count()

def enrichir_eleve(e: Eleve, db: Session) -> dict:
    return {
        "id": e.id, "nom": e.nom, "prenom": e.prenom,
        "classe": e.classe, "tel_parent": e.tel_parent,
        "nb_absences": compter(db, e.id, "absent"),
        "nb_retards":  compter(db, e.id, "retard"),
    }

def enrichir_absence(a: Absence, db: Session) -> dict:
    eleve = db.query(Eleve).filter(Eleve.id == a.eleve_id).first()
    return {
        "id": a.id, "eleve_id": a.eleve_id,
        "professeur_id": a.professeur_id,
        "type": a.type, "matiere": a.matiere,
        "classe": a.classe, "motif": a.motif,
        "heure": a.heure, "date": a.date,
        "valide": a.valide,
        "eleve_nom": f"{eleve.prenom} {eleve.nom}" if eleve else None,
    }

# ── ROUTES : ACCUEIL ───────────────────────────────────
@app.get("/")
def accueil():
    return {
        "message": "EduTrack API 🎓",
        "version": "1.0.0",
        "docs": "http://localhost:8000/docs"
    }

# ── ROUTES : AUTH ──────────────────────────────────────
@app.post("/auth/inscription", response_model=ProfesseurOut, status_code=201, tags=["Auth"])
def inscription(data: ProfesseurCreate, db: Session = Depends(get_db)):
    """Créer un compte professeur"""
    if db.query(Professeur).filter(Professeur.email == data.email).first():
        raise HTTPException(400, "Email déjà utilisé")
    prof = Professeur(
        nom=data.nom, prenom=data.prenom,
        email=data.email, mot_de_passe=hasher(data.mot_de_passe),
        matiere=data.matiere
    )
    db.add(prof); db.commit(); db.refresh(prof)
    return prof

@app.post("/auth/connexion", tags=["Auth"])
def connexion(data: LoginIn, db: Session = Depends(get_db)):
    """Connexion professeur"""
    prof = db.query(Professeur).filter(Professeur.email == data.email).first()
    if not prof or prof.mot_de_passe != hasher(data.mot_de_passe):
        raise HTTPException(401, "Email ou mot de passe incorrect")
    return {
        "token": secrets.token_hex(32) + f":{prof.id}",
        "professeur": {
            "id": prof.id, "nom": prof.nom,
            "prenom": prof.prenom, "email": prof.email,
            "matiere": prof.matiere
        }
    }

# ── ROUTES : ÉLÈVES ────────────────────────────────────
@app.get("/eleves", tags=["Élèves"])
def lister_eleves(
    recherche: Optional[str] = None,
    classe: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Liste tous les élèves"""
    q = db.query(Eleve).filter(Eleve.actif == True)
    if recherche:
        q = q.filter((Eleve.nom.ilike(f"%{recherche}%")) | (Eleve.prenom.ilike(f"%{recherche}%")))
    if classe:
        q = q.filter(Eleve.classe == classe)
    return [enrichir_eleve(e, db) for e in q.order_by(Eleve.nom).all()]

@app.get("/eleves/{eleve_id}", tags=["Élèves"])
def obtenir_eleve(eleve_id: int, db: Session = Depends(get_db)):
    """Détail d'un élève"""
    e = db.query(Eleve).filter(Eleve.id == eleve_id).first()
    if not e: raise HTTPException(404, "Élève introuvable")
    return enrichir_eleve(e, db)

@app.post("/eleves", status_code=201, tags=["Élèves"])
def creer_eleve(data: EleveCreate, db: Session = Depends(get_db)):
    """Ajouter un élève"""
    e = Eleve(**data.model_dump())
    db.add(e); db.commit(); db.refresh(e)
    return enrichir_eleve(e, db)

@app.put("/eleves/{eleve_id}", tags=["Élèves"])
def modifier_eleve(eleve_id: int, data: EleveCreate, db: Session = Depends(get_db)):
    """Modifier un élève"""
    e = db.query(Eleve).filter(Eleve.id == eleve_id).first()
    if not e: raise HTTPException(404, "Élève introuvable")
    for k, v in data.model_dump().items():
        setattr(e, k, v)
    db.commit(); db.refresh(e)
    return enrichir_eleve(e, db)

@app.delete("/eleves/{eleve_id}", status_code=204, tags=["Élèves"])
def supprimer_eleve(eleve_id: int, db: Session = Depends(get_db)):
    """Supprimer un élève"""
    e = db.query(Eleve).filter(Eleve.id == eleve_id).first()
    if not e: raise HTTPException(404, "Élève introuvable")
    e.actif = False; db.commit()

# ── ROUTES : ABSENCES ──────────────────────────────────
@app.get("/absences", tags=["Absences"])
def lister_absences(
    date_debut: Optional[str] = None,
    date_fin:   Optional[str] = None,
    classe:     Optional[str] = None,
    type:       Optional[str] = None,
    eleve_id:   Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Liste toutes les absences"""
    q = db.query(Absence)
    if date_debut: q = q.filter(Absence.date >= date_debut)
    if date_fin:   q = q.filter(Absence.date <= date_fin)
    if classe:     q = q.filter(Absence.classe == classe)
    if type:       q = q.filter(Absence.type == type)
    if eleve_id:   q = q.filter(Absence.eleve_id == eleve_id)
    return [enrichir_absence(a, db) for a in q.order_by(Absence.date.desc()).all()]

@app.get("/absences/aujourd-hui", tags=["Absences"])
def absences_aujourd_hui(db: Session = Depends(get_db)):
    """Absences du jour"""
    aujourd_hui = str(date.today())
    absences = db.query(Absence).filter(Absence.date == aujourd_hui).all()
    return [enrichir_absence(a, db) for a in absences]

@app.post("/absences", status_code=201, tags=["Absences"])
def enregistrer_absence(data: AbsenceCreate, db: Session = Depends(get_db)):
    """Enregistrer une absence ou un retard"""
    if not db.query(Eleve).filter(Eleve.id == data.eleve_id).first():
        raise HTTPException(404, "Élève introuvable")
    a = Absence(**data.model_dump())
    db.add(a); db.commit(); db.refresh(a)
    return enrichir_absence(a, db)

@app.delete("/absences/{absence_id}", status_code=204, tags=["Absences"])
def supprimer_absence(absence_id: int, db: Session = Depends(get_db)):
    """Supprimer une absence"""
    a = db.query(Absence).filter(Absence.id == absence_id).first()
    if not a: raise HTTPException(404, "Absence introuvable")
    db.delete(a); db.commit()

# ── ROUTES : STATISTIQUES ──────────────────────────────
@app.get("/stats/resume", tags=["Statistiques"])
def resume(db: Session = Depends(get_db)):
    """Résumé général"""
    aujourd_hui = str(date.today())
    return {
        "absences_total":       db.query(Absence).filter(Absence.type == "absent").count(),
        "retards_total":        db.query(Absence).filter(Absence.type == "retard").count(),
        "eleves_total":         db.query(Eleve).filter(Eleve.actif == True).count(),
        "absences_aujourd_hui": db.query(Absence).filter(Absence.date == aujourd_hui, Absence.type == "absent").count(),
        "retards_aujourd_hui":  db.query(Absence).filter(Absence.date == aujourd_hui, Absence.type == "retard").count(),
    }

@app.get("/stats/top-absents", tags=["Statistiques"])
def top_absents(db: Session = Depends(get_db)):
    """Élèves les plus absents"""
    eleves = db.query(Eleve).filter(Eleve.actif == True).all()
    result = []
    for e in eleves:
        nb = compter(db, e.id, "absent")
        if nb > 0:
            result.append({
                "eleve_id": e.id,
                "nom": f"{e.prenom} {e.nom}",
                "classe": e.classe,
                "nb_absences": nb,
                "nb_retards": compter(db, e.id, "retard"),
                "alerte": nb >= 5,
            })
    return sorted(result, key=lambda x: x["nb_absences"], reverse=True)

@app.get("/stats/alertes", tags=["Statistiques"])
def alertes(db: Session = Depends(get_db)):
    """Élèves avec 5 absences ou plus"""
    eleves = db.query(Eleve).filter(Eleve.actif == True).all()
    result = []
    for e in eleves:
        nb = compter(db, e.id, "absent")
        if nb >= 5:
            result.append({
                "eleve_id": e.id,
                "nom": f"{e.prenom} {e.nom}",
                "classe": e.classe,
                "nb_absences": nb,
                "tel_parent": e.tel_parent,
            })
    return result

# ── LANCEMENT ──────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  EduTrack API — Démarrage")
    print("="*50)
    print("  → http://localhost:8000")
    print("  → http://localhost:8000/docs  (documentation)")
    print("="*50 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
