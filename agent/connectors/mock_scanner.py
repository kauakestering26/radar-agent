"""
Mock Scanner — simula a descoberta de assets de IA
sem precisar de credenciais ou sistemas reais.

Em produção, cada conector teria seu próprio módulo
(postgresql.py, github.py, kubernetes.py, etc.)
"""

import asyncio
import random
from datetime import datetime


MOCK_ASSETS = [
    {
        "type": "llm_api_key",
        "connector": "mock",
        "name": "OPENAI_API_KEY em variável de ambiente",
        "detail": "Chave OpenAI detectada em env var OPENAI_API_KEY",
        "confidence": 0.99,
        "severity": "high",
    },
    {
        "type": "fine_tuned_model",
        "connector": "mock",
        "name": "ft:gpt-3.5-turbo:acme:custom-model:abc123",
        "detail": "Modelo fine-tuned registrado na conta OpenAI",
        "confidence": 0.95,
        "severity": "medium",
    },
    {
        "type": "embedding_store",
        "connector": "mock",
        "name": "Tabela 'document_embeddings' (dim=1536)",
        "detail": "Coluna vector(1536) compatível com embeddings OpenAI text-embedding-ada-002",
        "confidence": 0.91,
        "severity": "medium",
    },
    {
        "type": "ml_pipeline",
        "connector": "mock",
        "name": "Pipeline de treinamento detectado",
        "detail": "requirements.txt contém torch==2.2.0, transformers==4.38.0",
        "confidence": 0.87,
        "severity": "low",
    },
    {
        "type": "ai_endpoint",
        "connector": "mock",
        "name": "Endpoint /api/v1/chat",
        "detail": "Rota que encaminha para OpenAI /v1/chat/completions",
        "confidence": 0.82,
        "severity": "medium",
    },
    {
        "type": "model_registry",
        "connector": "mock",
        "name": "MLflow Model Registry",
        "detail": "3 modelos registrados: sentiment-v1, classifier-v2, recommender-v1",
        "confidence": 0.94,
        "severity": "low",
    },
]


async def scan(config: dict) -> list[dict]:
    """
    Executa o scan mock.
    Simula latência de rede e retorna um subconjunto aleatório de assets.
    """
    await asyncio.sleep(random.uniform(1.0, 2.5))  # simula tempo de scan

    # Simula encontrar entre 2 e 6 assets
    n = random.randint(2, len(MOCK_ASSETS))
    discovered = random.sample(MOCK_ASSETS, n)

    # Adiciona timestamp e id únicos
    for asset in discovered:
        asset = asset.copy()
        asset["discovered_at"] = datetime.utcnow().isoformat()

    return discovered
