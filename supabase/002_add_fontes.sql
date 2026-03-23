-- Adiciona novos valores ao enum fonte_tipo (se não existirem)
-- Postgres permite ALTER TYPE ... ADD VALUE
do $$
begin
    if not exists (select 1 from pg_enum where enumlabel = 'QUERIDO_DIARIO' and enumtypid = (select oid from pg_type where typname = 'fonte_tipo')) then
        alter type fonte_tipo add value 'QUERIDO_DIARIO';
    end if;
    if not exists (select 1 from pg_enum where enumlabel = 'TCE_RJ' and enumtypid = (select oid from pg_type where typname = 'fonte_tipo')) then
        alter type fonte_tipo add value 'TCE_RJ';
    end if;
end$$;
