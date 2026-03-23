-- Atualiza defaults do user_config para incluir mais UFs e termos de email

ALTER TABLE user_config
  ALTER COLUMN ufs SET DEFAULT '{MG,RJ,SP,ES,PR,SC,RS,GO,BA,PE,CE}';

ALTER TABLE user_config
  ALTER COLUMN palavras_chave SET DEFAULT '{software,"permissão de uso","licença de uso","locação de software","cessão de uso","sistema integrado","sistema de gestão","solução tecnológica","informática","tecnologia da informação",email,e-mail,"e-mails institucionais","hospedagem de e-mails"}';
