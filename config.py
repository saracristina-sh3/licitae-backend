import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

    # PNCP API
    PNCP_BASE_URL = "https://pncp.gov.br/api/consulta"

    # Email
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    EMAIL_DESTINATARIOS = [
        e.strip() for e in os.getenv("EMAIL_DESTINATARIOS", "").split(",") if e.strip()
    ]

    # Relatórios
    RELATORIOS_DIR = os.getenv("RELATORIOS_DIR", "./relatorios")

    # Busca
    PALAVRAS_CHAVE = [
        p.strip()
        for p in os.getenv(
            "PALAVRAS_CHAVE",
            "software,sistema,permissão de uso,licença de uso,solução tecnológica,gestão pública,sistema de gestão,locação de software,cessão de uso,sistema integrado,email,e-mail,e-mails institucionais,hospedagem de e-mails",
        ).split(",")
        if p.strip()
    ]

    DIAS_RETROATIVOS = int(os.getenv("DIAS_RETROATIVOS", "7"))

    UFS = [u.strip() for u in os.getenv("UFS", "MG,RJ,SP,ES,PR,SC,RS,GO,BA,PE,CE").split(",")]

    POPULACAO_MAXIMA = int(os.getenv("POPULACAO_MAXIMA", "91692"))

    # Modalidades relevantes para licitação de software
    MODALIDADES = [
        6,   # Pregão Eletrônico
        7,   # Pregão Presencial
        8,   # Dispensa de Licitação
        9,   # Inexigibilidade
        12,  # Credenciamento
    ]

    # PNCP API (compras — itens e resultados)
    PNCP_COMPRAS_URL = "https://pncp.gov.br/api/pncp"

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Plataformas-alvo para coleta de itens (idUsuario PNCP)
    PLATAFORMAS_ALVO = [
        int(x) for x in os.getenv(
            "PLATAFORMAS_ALVO",
            "121,12,13,18,82,84,55,100,3",
        ).split(",") if x.strip()
    ]
