-- Adiciona controle de envio de email nos convites
ALTER TABLE org_convites ADD COLUMN IF NOT EXISTS email_enviado boolean DEFAULT false;
ALTER TABLE org_convites ADD COLUMN IF NOT EXISTS nome_convidante text;
ALTER TABLE org_convites ADD COLUMN IF NOT EXISTS nome_organizacao text;
