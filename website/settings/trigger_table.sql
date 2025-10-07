create trigger tg_user after insert or delete or update on app.user for each row execute procedure app.create_audit_log('true');
create trigger tg_type_user after insert or delete or update on app.user_type for each row execute procedure app.create_audit_log('true');
create trigger tg_research_line after insert or delete or update on app.research_line for each row execute procedure app.create_audit_log('true');
create trigger tg_project after insert or delete or update on app.project for each row execute procedure app.create_audit_log('true');
create trigger tg_project_team after insert or delete or update on app.project_team for each row execute procedure app.create_audit_log('true');
create trigger tg_code_export after insert or delete or update on app.code_export for each row execute procedure app.create_audit_log('true');
create trigger tg_caqdas after insert or delete or update on app.caqdas for each row execute procedure app.create_audit_log('true');