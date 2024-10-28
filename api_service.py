# api_service.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime, timedelta
from firebase_admin import credentials, firestore, initialize_app
from google.cloud.firestore_v1 import FieldFilter
import firebase_admin

app = FastAPI()

# Dicionários para armazenar os clientes Firestore, caches locais e listeners por FLET_PATH
clients: Dict[str, firestore.Client] = {}
caches: Dict[str, Dict] = {}
listeners: Dict[str, any] = {}

class RegisterBarbearia(BaseModel):
    flet_path: str
    cred: dict

class CacheData(BaseModel):
    daily_revenue: float
    daily_transactions: int
    weekly_revenue: float
    weekly_transactions: int
    last_update: datetime

def initialize_firestore_client(cred_data):
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_data)
        app = initialize_app(cred)
    else:
        app = firebase_admin.get_app()
    
    return firestore.client(app)

def get_all_collaborator_ids(db):
    collaborator_ids = []
    collaborators_ref = db.collection("colaborador")
    collaborators = collaborators_ref.stream()
    
    for collaborator in collaborators:
        collaborator_ids.append(collaborator.id)
    
    return collaborator_ids

def save_cache_to_firestore(db, cache_data):
    # Verifica se todos os IDs de colaboradores estão presentes no cache
    all_collaborator_ids = get_all_collaborator_ids(db)
    
    for colaborador_id in all_collaborator_ids:
        if colaborador_id not in cache_data:
            cache_data[colaborador_id] = {
                "daily_revenue": 0,
                "daily_transactions": 0,
                "weekly_revenue": 0,
                "weekly_transactions": 0,
                "last_update": datetime.now()
            }

    cache_ref = db.collection("cache").document("revenue_cache")
    cache_ref.set(cache_data)

def load_cache_from_firestore(db, flet_path):
    global caches
    cache_ref = db.collection("cache").document("revenue_cache")
    cache_doc = cache_ref.get()
    if cache_doc.exists:
        caches[flet_path] = cache_doc.to_dict()
    else:
        caches[flet_path] = {}
    return caches[flet_path]

def calculate_daily_revenue(db):
    now = datetime.now()
    data_formatada = now.strftime('%d-%m-%Y')
    ano = now.year
    mes = now.month
    
    transacoes_ref = db.collection("transacoes").document(str(ano)).collection(str(mes).zfill(2))
    query = transacoes_ref.where(filter=FieldFilter("data", "==", data_formatada))
    transactions = query.stream()

    daily_revenue = {}

    for transaction in transactions:
        data = transaction.to_dict()
        colaborador_id = data['colaborador_id']
        total = data['total']
        
        if colaborador_id not in daily_revenue:
            daily_revenue[colaborador_id] = {"total_value": 0, "total_transactions": 0}
        
        daily_revenue[colaborador_id]["total_value"] += total
        daily_revenue[colaborador_id]["total_transactions"] += 1
    
    return daily_revenue

def calculate_weekly_revenue(db):
    now = datetime.now()

    # Calcular a data de início e fim da semana atual
    start_of_week = now - timedelta(days=now.weekday())  # Segunda-feira
    end_of_week = start_of_week + timedelta(days=6)  # Domingo

    weekly_revenue = {}

    # Iterar por cada dia da semana atual
    current_day = start_of_week
    while current_day <= end_of_week:
        data_formatada = current_day.strftime('%d-%m-%Y')
        mes_atual = current_day.month
        ano_atual = current_day.year

        transacoes_ref = db.collection("transacoes").document(str(ano_atual)).collection(str(mes_atual).zfill(2))
        query = transacoes_ref.where(filter=FieldFilter("data", "==", data_formatada))
        transactions = query.stream()

        for transaction in transactions:
            data = transaction.to_dict()
            colaborador_id = data['colaborador_id']
            total = data['total']
            
            if colaborador_id not in weekly_revenue:
                weekly_revenue[colaborador_id] = {"total_value": 0, "total_transactions": 0}
            
            weekly_revenue[colaborador_id]["total_value"] += total
            weekly_revenue[colaborador_id]["total_transactions"] += 1

        current_day += timedelta(days=1)  # Próximo dia
    
    return weekly_revenue

def on_transaction_update(doc_snapshot, changes, read_time, flet_path, db):
    # cache = load_cache_from_firestore(db, flet_path)
    # print(f"Alteração detectada no Firestore para {flet_path}.")

    # daily_revenue = calculate_daily_revenue(db)
    # weekly_revenue = calculate_weekly_revenue(db)
    
    # for colaborador_id in weekly_revenue:
    #     cache[colaborador_id] = {
    #         "daily_revenue": daily_revenue[colaborador_id]["total_value"],
    #         "daily_transactions": daily_revenue[colaborador_id]["total_transactions"],
    #         "weekly_revenue": weekly_revenue.get(colaborador_id, {"total_value": 0})["total_value"],
    #         "weekly_transactions": weekly_revenue.get(colaborador_id, {"total_transactions": 0})["total_transactions"],
    #         "last_update": datetime.now()
    #     }

    # save_cache_to_firestore(db, cache)

    cache = load_cache_from_firestore(db, flet_path)
    print(f"Alteração detectada no Firestore para {flet_path}.")

    daily_revenue = calculate_daily_revenue(db)
    weekly_revenue = calculate_weekly_revenue(db)
    
    for colaborador_id in get_all_collaborator_ids(db):
        daily_data = daily_revenue.get(colaborador_id, {"total_value": 0, "total_transactions": 0})
        weekly_data = weekly_revenue.get(colaborador_id, {"total_value": 0, "total_transactions": 0})
        
        cache[colaborador_id] = {
            "daily_revenue": daily_data["total_value"],
            "daily_transactions": daily_data["total_transactions"],
            "weekly_revenue": weekly_data["total_value"],
            "weekly_transactions": weekly_data["total_transactions"],
            "last_update": datetime.now()
        }


def start_transaction_listener(flet_path, db):
    now = datetime.now()
    ano = now.year
    mes = now.month
    transacoes_ref = db.collection("transacoes").document(str(ano)).collection(str(mes).zfill(2))
    listener = transacoes_ref.on_snapshot(lambda doc_snapshot, changes, read_time: 
                                           on_transaction_update(doc_snapshot, changes, read_time, flet_path, db))
    listeners[flet_path] = listener

@app.post("/register")
def register_barbearia(barbearia: RegisterBarbearia):
    if barbearia.flet_path in clients:
        raise HTTPException(status_code=400, detail="Barbearia já registrada.")

    db = initialize_firestore_client(barbearia.cred)
    
    # Armazena o cliente Firestore
    clients[barbearia.flet_path] = db
    
    # Carrega o cache inicial do Firestore para esta barbearia
    load_cache_from_firestore(db, barbearia.flet_path)

    # Inicia o listener para esta barbearia
    start_transaction_listener(barbearia.flet_path, db)
    
    return {"status": f"Barbearia {barbearia.flet_path} registrada com sucesso."}

@app.get("/cache/{flet_path}")
def get_revenue_from_cache(flet_path: str):
    if flet_path not in clients:
        raise HTTPException(status_code=404, detail="Barbearia não encontrada.")

    cache = caches.get(flet_path, {})
    total_daily_value = sum(data["daily_revenue"] for data in cache.values())
    total_weekly_value = sum(data["weekly_revenue"] for data in cache.values())
    total_daily_transactions = sum(data["daily_transactions"] for data in cache.values())
    total_weekly_transactions = sum(data["weekly_transactions"] for data in cache.values())
    
    return (
        total_daily_value,
        total_weekly_value,
        total_daily_transactions,
        total_weekly_transactions
    )

@app.get("/cache/{flet_path}/{colaborador_id}")
def get_revenue_from_cache(flet_path: str, colaborador_id: str):
    if flet_path not in clients:
        raise HTTPException(status_code=404, detail="Barbearia não encontrada.")

    cache = caches.get(flet_path, {})
    db = clients[flet_path]

    if colaborador_id not in get_all_collaborator_ids(db):
        return 0, 0, 0, 0

    colaborador_cache = cache.get(colaborador_id, {})
    data = colaborador_cache.get('last_update', "nenhum dado")
    data_formatada = data.strftime('%d-%m-%Y')
    print(data)
    print(colaborador_cache)
    print(data_formatada)

    data_atual_formatada = datetime.now().strftime('%d-%m-%Y')
    print(data_atual_formatada)

    if data_atual_formatada != data_formatada:
        print("Oi")
        daily_revenue = calculate_daily_revenue(db)
        weekly_revenue = calculate_weekly_revenue(db)
        
        for colaborador in daily_revenue:
            cache[colaborador] = {
                "daily_revenue": daily_revenue[colaborador]["total_value"],
                "daily_transactions": daily_revenue[colaborador]["total_transactions"],
                "weekly_revenue": weekly_revenue.get(colaborador, {"total_value": 0})["total_value"],
                "weekly_transactions": weekly_revenue.get(colaborador, {"total_transactions": 0})["total_transactions"],
                "last_update": datetime.now()
            }

        save_cache_to_firestore(db, cache)
    
    colaborador_cache = cache.get(colaborador_id, {})
    return (
        colaborador_cache.get("daily_revenue", 0),
        colaborador_cache.get("weekly_revenue", 0),
        colaborador_cache.get("daily_transactions", 0),
        colaborador_cache.get("weekly_transactions", 0)
    )

