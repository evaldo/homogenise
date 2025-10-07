CREATE OR REPLACE FUNCTION app.create_audit_log()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
	client_query text;
	rec_fields record;
	cur_fields refcursor;
	value_previous varchar(200);
	value_later varchar(200);		
begin		
    IF TG_WHEN <> 'AFTER' THEN
        RAISE EXCEPTION 'app.create_audit_log is a function that can only to execute as AFTER trigger.';
    END IF;
    IF NOT TG_ARGV[0]::boolean IS DISTINCT FROM 'f'::boolean THEN
        client_query = NULL;
    END IF;    
    IF TG_OP IN ('INSERT', 'UPDATE', 'DELETE') AND TG_LEVEL = 'ROW' then	
		open cur_fields for
		select column_name as field_table_bd from information_schema."columns" c where c.table_schema = TG_TABLE_SCHEMA::text and c.table_name  = TG_TABLE_NAME::text;
		loop	    
		    fetch cur_fields into rec_fields;
	    		exit when not found;					
				EXECUTE format('SELECT ($1).%s::text', rec_fields.field_table_bd) USING OLD into value_previous ;						
				EXECUTE format('SELECT ($1).%s::text', rec_fields.field_table_bd) USING NEW INTO  value_later;	        			
				INSERT INTO app.audit_log (		
				  auditlog_id
				, table_name
				, column_table								
				, dt_auditlog
				, action_type
				, old_data_column
				, new_data_column)
				VALUES (
				  nextval('app.audit_log_auditlog_id_seq')
				, TG_TABLE_NAME::text
				, rec_fields.field_table_bd				
				, CURRENT_TIMESTAMP
				, substring(TG_OP,1,1)
				, value_previous
				, value_later
				);		        	   
	   	end loop;	   
	    close cur_fields;	
    ELSE
        RAISE EXCEPTION '[app.create_audit_log] - Function added as trigger app/homogenise case is not mentioned: %, %',TG_OP, TG_LEVEL;
        RETURN NULL;
    END IF;    
    RETURN NULL;
END;
$function$;

