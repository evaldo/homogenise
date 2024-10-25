import urllib.request
import shutil
from flask import Blueprint, redirect, render_template, request, flash, url_for
from flask_login import login_required, current_user
from website import models
from website.settings import db
from werkzeug.security import generate_password_hash

views = Blueprint('views', __name__)

@views.route('/')
@login_required
def home():
    return render_template("home.html", user=current_user)


@views.route('/projectteam', methods=['GET', 'POST'])
@login_required
def projectteam():

    cur=db.get_cursor()

    if request.method == 'POST': 
        project_search = request.form.get('project_search') #Gets the note from the HTML 
        if len(project_search) < 1:            
            return redirect(url_for('views.projectteam'))
        else:
            cur.execute("select ptm.project_team_id " +
                    "     , prj.project_name " +
                    "     , usr.first_name " +
                    "     , case when ptm.st_user_leader = 1 then 'X' else '' end st_user_leader " +
                    "from app.project prj " +
                    "     , app.user usr " +
                    "     , app.project_team ptm " +
                    "where prj.project_id = ptm.project_id " +
                    "  and usr.id = ptm.user_id " +                     
                    "  and upper(project_name) like upper('%" + request.form.get("project_search") + "%')" +
                    " order by prj.project_name asc, ptm.st_user_leader desc, usr.first_name asc")
            data = cur.fetchall()
            cur.close
            return render_template("projectteam.html", output_data = data, user=current_user)        
    else:    
        cur.execute("select ptm.project_team_id " +
                    "     , prj.project_name " +
                    "     , usr.first_name " +
                    "     , case when ptm.st_user_leader = 1 then 'X' else '' end st_user_leader " +
                    "from app.project prj " +
                    "     , app.user usr " +
                    "     , app.project_team ptm " +
                    "where prj.project_id = ptm.project_id " +
                    "  and usr.id = ptm.user_id " + 
                    " order by prj.project_name asc, ptm.st_user_leader desc, usr.first_name asc")
        
        data = cur.fetchall()
        cur.close
        return render_template("projectteam.html", output_data = data, user=current_user)

@views.route('/modifyuser', methods=['GET', 'POST'])
@login_required
def modifyuser():

    cur=db.get_cursor()

    if request.method == 'POST': 
        project_search = request.form.get('username_search') #Gets the note from the HTML
        if len(project_search) < 1:                                              
            cur.execute("select id, first_name, email, user_type_id from app.user order by first_name")
            data = cur.fetchall()
            cur.close        
            return render_template("modifyuser.html", output_data = data, user=current_user)   
        else:
            cur.execute("select id, first_name, email, user_type_id from app.user  where upper(first_name) like upper('%" + request.form.get('username_search') + "%') order by first_name")
            data = cur.fetchall()
            cur.close
            return render_template("modifyuser.html", output_data = data, user=current_user)
    else:
        cur.execute("select id, first_name, email, user_type_id from app.user order by first_name")
        data = cur.fetchall()
        cur.close
        return render_template("modifyuser.html", output_data = data, user=current_user)
    

@views.route('/usertype', methods=['GET', 'POST'])
@login_required
def usertype():
    if request.method == 'POST': 
        usertype_search = request.form.get('usertype_search') #Gets the note from the HTML 
        if len(usertype_search) < 1:    
            cur=db.get_cursor()                        
            cur.execute("SELECT * FROM app.user_type  order by user_type_name")
            data = cur.fetchall()
            cur.close        
            return render_template("usertype.html", output_data = data, user=current_user)     
        else:
            cur=db.get_cursor()                        
            cur.execute("SELECT * FROM app.user_type where upper(user_type_name) like upper('%" + request.form.get("usertype_search") + "%') order by user_type_name")
            data = cur.fetchall()
            cur.close
            return render_template("usertype.html", output_data = data, user=current_user)  

    else:                  
        cur=db.get_cursor()
        cur.execute("SELECT * FROM app.user_type order by user_type_name")
        data = cur.fetchall()

        cur.close

        return render_template("usertype.html", output_data = data, user=current_user)

@views.route('/researchline', methods=['GET', 'POST'])
@login_required
def researchline():
    if request.method == 'POST':
        researchline_search = request.form.get('researchline_search') #Gets the note from the HTML 
        if len(researchline_search) < 1:    
            cur=db.get_cursor()                        
            cur.execute("SELECT * FROM app.research_line  order by research_line_name")
            data = cur.fetchall()
            cur.close        
            return render_template("researchline.html", output_data = data, user=current_user)     
        else:
            cur=db.get_cursor()                        
            cur.execute("SELECT * FROM app.research_line where upper(research_line_name) like upper('%" + request.form.get("researchline_search") + "%') order by research_line_name")
            data = cur.fetchall()
            cur.close
            return render_template("researchline.html", output_data = data, user=current_user)        
    else:

        cur=db.get_cursor()
        cur.execute("SELECT * FROM app.research_line order by research_line_name")
        data = cur.fetchall()

        cur.close

        return render_template("researchline.html", output_data = data, user=current_user)


@views.route('/usertypedata', methods= ['GET', 'POST'])
def usertypedata(): 

    cur=db.get_cursor()
    cur.execute("SELECT * FROM app.user_type order by user_type_name")
    data = cur.fetchall()

    if request.method == 'POST':                 
        user_type_id = request.form.get("user_type_id")
        user_type_name = request.form.get("user_type_name")

        if request.args.get('type_operation', '') == 'D':
            user_user_type = [0]  
            user_user_type_item = 0          
            cur.execute("SELECT count(0) FROM app.user where user_type_id = " + user_type_id)    
            user_user_type = cur.fetchall()
            user_user_type_item = [user_user_type_item[0] for user_user_type_item in user_user_type]

            if int(user_user_type_item[0]) > 0:  
                flash('There are users using this user type!', category='error')
                return redirect(url_for('views.usertype'))
            
            else:
                cur.execute("update app.user_type set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where user_type_id = " + user_type_id)
                cur.execute("delete from app.user_type where user_type_id = " + user_type_id)            
                flash('Data deleted!', category='success')
                return redirect(url_for('views.usertype'))

        if request.args.get('type_operation', '') == 'A': 
            
            cur.execute("insert into app.user_type (user_type_id, user_type_name, user_id_log, user_name_log) values (nextval('app.user_type_user_type_id_seq'), '" + user_type_name + "', " + current_user.get_id()  + ", '" + current_user.first_name  + "')")            
            flash('Data inserted!', category='success')
            return redirect(url_for('views.usertype'))

        if request.args.get('type_operation', '') == 'U':
            cur.execute("update app.user_type set user_type_name = '" + user_type_name + "', user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where user_type_id = " + user_type_id)
            flash('Data updated!', category='success')
            return redirect(url_for('views.usertype'))
        
        cur.close
        return render_template("usertype.html", output_data = data, user=current_user)                

    if request.method == 'GET':              

        user_type_id = request.args.get('user_type_id', '') 
        user_type_name = request.args.get('user_type_name', '') 

        if request.args.get('type_operation', '') == 'D':
            type_operation = 'Delete'
        elif request.args.get('type_operation', '') == 'U':
            type_operation = 'Update'
        else:
            type_operation = 'Add'

        cur=db.get_cursor()
        cur.execute("select user_type_id, user_type_name from app.user_type order by user_type_name")
        data_user_type= cur.fetchall()            

        cur.close

        return render_template("usertypedata.html", user=current_user, user_type_id = user_type_id, user_type_name = user_type_name,  usertype_list = data_user_type, type_operation = type_operation)         


@views.route('/researchlinedata', methods= ['GET', 'POST'])
def researchlinedata(): 

    if request.method == 'POST':   

        cur=db.get_cursor()

        research_line_id = request.form.get("research_line_id")
        research_line_name = request.form.get("research_line_name")

        if request.args.get('type_operation', '') == 'D':
            research_line_project = [0]  
            research_line_project_item = 0          
            cur.execute("SELECT count(0) FROM app.project where research_line_id = " + research_line_id)    
            research_line_project = cur.fetchall()
            research_line_project_item = [research_line_project_item[0] for research_line_project_item in research_line_project]

            if int(research_line_project_item[0]) > 0:  
                flash('There are projects using this research line!', category='error')
                return redirect(url_for('views.researchline'))
            
            else:
                cur.execute("update app.research_line set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where research_line_id = " + research_line_id)
                cur.execute("delete from app.research_line where research_line_id = " + research_line_id)            
                flash('Data deleted!', category='success')
                return redirect(url_for('views.researchline'))

        if request.args.get('type_operation', '') == 'A':            
            cur.execute("insert into app.research_line (research_line_name, user_id_log, user_name_log) values ('" + research_line_name + "', " + current_user.get_id()  + ", '" + current_user.first_name  + "')")            
            flash('Data inserted!', category='success')
            return redirect(url_for('views.researchline'))

        if request.args.get('type_operation', '') == 'U':
            cur.execute("update app.research_line set research_line_name = '" + research_line_name + "', user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "' where research_line_id = " + research_line_id)
            flash('Data updated!', category='success')
            return redirect(url_for('views.researchline'))
        
        cur.execute("SELECT * FROM app.research_line order by research_line_name")
        data = cur.fetchall()
        cur.close
        return render_template("researchline.html", output_data = data, user=current_user)        

    if request.method == 'GET':              

        research_line_id = request.args.get('research_line_id', '') 
        research_line_name = request.args.get('research_line_name', '') 

        if request.args.get('type_operation', '') == 'D':
            type_operation = 'Delete'
        elif request.args.get('type_operation', '') == 'U':
            type_operation = 'Update'
        else:
            type_operation = 'Add'

        cur=db.get_cursor()
        cur.execute("select research_line_id, research_line_name from app.research_line order by research_line_name")
        data_research_line= cur.fetchall()            

        cur.close

        return render_template("researchlinedata.html", user=current_user, research_line_id = research_line_id, research_line_name = research_line_name,  researchline_list = data_research_line, type_operation = type_operation)         

@views.route('/projectresearch', methods=['GET', 'POST'])
@login_required
def projectresearch():
    if request.method == 'POST': 
        project_search = request.form.get('project_search') #Gets the note from the HTML 
        if len(project_search) < 1:    
            cur=db.get_cursor()                        
            cur.execute("SELECT * FROM app.project order by project_name")
            data = cur.fetchall()
            cur.close        
            return render_template("projectresearch.html", output_data = data, user=current_user)     
        else:
            cur=db.get_cursor()                        
            cur.execute("SELECT * FROM app.project where upper(project_name) like upper('%" + request.form.get("project_search") + "%') order by project_name")
            data = cur.fetchall()
            cur.close
            return render_template("projectresearch.html", output_data = data, user=current_user)    
    else:
        cur=db.get_cursor()
        cur.execute("SELECT * FROM app.project order by project_name")
        data = cur.fetchall()

        cur.close

        return render_template("projectresearch.html", output_data = data, user=current_user)

@views.route('/projectdata', methods= ['GET', 'POST'])
def projectdata(): 

    if request.method == 'POST':
         
        cur=db.get_cursor()
        project_id = request.form.get("project_id")
        project_name = request.form.get("project_name")
        project_description = request.form.get("project_description")
        research_line_id = request.form.get("research_line_id")

        if research_line_id == 'null':
            flash('Fill out all data to execute transaction!', category='error')
        else:
            if request.args.get("type_operation") == 'D':            
                project_team = [0]  
                project_team_item = 0          
                cur.execute("SELECT count(0) FROM app.project_team where project_id = " + project_id)    
                project_team = cur.fetchall()
                project_team_item = [project_team_item_item[0] for project_team_item_item in project_team]

                if int(project_team_item[0]) > 0:  
                    flash('There are project teams using this project!', category='error')
                    return redirect(url_for('views.projectresearch'))
                else:
                    cur.execute("update app.project set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where project_id = " + project_id)
                    cur.execute("delete from app.project where project_id = " + project_id)            
                    flash('Data deleted!', category='success')
                    return redirect(url_for('views.projectresearch'))
                
            if request.args.get('type_operation', '') == 'A':                            
                cur.execute("insert into app.project (project_id, project_name, project_description, research_line_id, user_id_log, user_name_log) values (nextval('app.project_project_id_seq'), '" + project_name + "', '" + project_description +  "' , " + research_line_id + ", " + current_user.get_id()  + ", '" + current_user.first_name  + "')")            
                flash('Data inserted!', category='success')
                return redirect(url_for('views.projectresearch'))
            
            if request.args.get('type_operation', '') == 'U':            
                cur.execute("update app.project set project_name = '" + project_name + "', project_description = '" + project_description + "' , research_line_id = " + research_line_id + ", user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "' where project_id = " + project_id)
                flash('Data updated!', category='success')
                return redirect(url_for('views.projectresearch'))
            
        cur.execute("SELECT * FROM app.project order by project_name")
        data = cur.fetchall()
        cur.close
        return render_template("projectresearch.html", output_data = data, user=current_user)                

    if request.method == 'GET':
        project_id = request.args.get('project_id', '') 
        project_name = request.args.get('project_name', '') 
        project_description = request.args.get('project_description', '') 

        if request.args.get('type_operation', '') == 'D':
            type_operation = 'Delete'
        elif request.args.get('type_operation', '') == 'U':
            type_operation = 'Update'
        else:
            type_operation = 'Add'

        cur=db.get_cursor()

        research_line_name = [0]        
        
        if project_id != '':        
            cur.execute("select rsh.research_line_name " 
                        "from app.project prj "
                        "   , app.research_line rsh "
                        "where rsh.research_line_id = prj.research_line_id "
                        "and prj.project_id = " + project_id + "")        
            research_line_name_project = cur.fetchall()
            research_line_name = [research_line_name_project_item[0] for research_line_name_project_item in research_line_name_project]
                         
        cur.execute("select research_line_id, research_line_name from app.research_line order by research_line_name")
        data_research_line= cur.fetchall()            

        cur.close

        return render_template("projectdata.html", user=current_user, project_id = project_id, project_name = project_name, project_description = project_description, researchline_name = research_line_name[0], researchline_list = data_research_line, type_operation = type_operation)         

@views.route('/modifyuserdata', methods= ['GET', 'POST'])
def modifyuserdata(): 

    if request.method == 'POST':       
        user_id = request.form.get('user_id', '')
        user_type_id = request.form.get("user_type_id")
        first_name = request.form.get("first_name")
        password1 = request.form.get("password1")
        password2 = request.form.get("password2")

        cur=db.get_cursor()

        if request.args.get('type_operation', '') == 'D':

            project_team = [0]  
            project_team_item = 0          
            cur.execute("SELECT count(0) FROM app.project_team where user_id = " + user_id)    
            project_team = cur.fetchall()
            project_team_item = [project_team_item_item[0] for project_team_item_item in project_team]

            if int(project_team_item[0]) > 0:  
                flash('There are project teams using this user!', category='error')
                return redirect(url_for('views.modifyuser'))
            
            else:
                cur.execute("update app.user set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where id = " + user_id)
                cur.execute("delete from app.user where id = " + user_id)            
                flash('Data deleted!', category='success')
                return redirect(url_for('views.modifyuser'))

        if request.args.get('type_operation', '') == 'U':
                        
            if password1 != password2:
                flash('Passwords don\'t match.', category='error')
                return redirect(url_for('views.modifyuser'))

            elif len(password1) < 7:
                flash('Password must be at least 7 characters.', category='error')
                return redirect(url_for('views.modifyuser'))

            else:                
                cur.execute("update app.user set first_name = '" + first_name + "', user_type_id = " + user_type_id + ", password = '" + generate_password_hash(
                password1, method='pbkdf2:sha256') + "', user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where id = " + user_id)
                flash('Data updated!', category='success')
                return redirect(url_for('views.modifyuser'))
   
        cur=db.get_cursor()
        cur.execute("select id, first_name, email, user_type_id from app.user order by first_name")
        data = cur.fetchall()

        cur.close

        return render_template("modifyuser.html", output_data = data, user=current_user)        

    if request.method == 'GET':
        user_id = request.args.get('user_id', '')
        first_name = request.args.get('first_name', '') 
        email = request.args.get('email', '') 

        if request.args.get('type_operation', '') == 'D':
            type_operation = 'Delete'
        else:
            request.args.get('type_operation', '') == 'U'
            type_operation = 'Update'       

        cur=db.get_cursor()
        user_type_name_user = [0]                        
        
        cur.execute("select ust.user_type_name " 
                        " from app.user usr "
                        "   , app.user_type ust "
                        " where usr.user_type_id = ust.user_type_id "
                        " and usr.id = " + user_id + "")                
        user_type_name = cur.fetchall()
        if len(user_type_name) > 0:
            user_type_name_user = [user_type_name_item[0] for user_type_name_item in user_type_name]
                         
        cur.execute("select * from app.user_type order by 2")
        data_user_type= cur.fetchall()            

        cur.close

        return render_template("modifyuserdata.html", user=current_user
                                                    , user_id = user_id
                                                    , first_name = first_name
                                                    , email = email
                                                    , user_type_name = user_type_name_user[0]
                                                    , usertype_list = data_user_type
                                                    , type_operation = type_operation)         
    
@views.route('/projectteamdata', methods= ['GET', 'POST'])
def projectTeamData(): 

    if request.method == 'POST':        

        cur=db.get_cursor()

        project_team_id = request.form.get("project_team_id")
        project_id = request.form.get("project_id")
        user_id = request.form.get("user_id")
        st_user_leader = request.form.get("st_user_leader")

        project_team = [0]  
        project_team_item = 0          
        cur.execute("SELECT count(0) FROM app.project_team where user_id = " + user_id + " and project_id = " + project_id + "")    
        project_team = cur.fetchall()
        project_team_item = [project_team_item_item[0] for project_team_item_item in project_team]

        if project_id == 'null' or user_id == 'null' or st_user_leader == 'null':
            flash('Fill out all data to execute transaction!', category='error')
            return redirect(url_for('views.projectteam'))

        else:
            if request.args.get("type_operation") == 'D':
                cur.execute("update app.project_team set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where project_team_id = " + project_team_id)
                cur.execute("delete from app.project_team where project_team_id = " + project_team_id)            
                flash('Data deleted!', category='success')
                return redirect(url_for('views.projectteam'))

            if request.args.get("type_operation") == 'A':            

                if int(project_team_item[0]) > 0:  
                    flash('Already there is a project for this user!', category='error')
                    return redirect(url_for('views.projectteam'))

                else:
                    cur.execute("INSERT INTO app.project_team(project_team_id, project_id, user_id, st_user_leader, user_id_log, user_name_log)	VALUES (nextval('app.project_team_project_team_id_seq'), " + project_id + ", " + user_id + ", " + st_user_leader + ", " + current_user.get_id()  + ", '" + current_user.first_name  + "')")            
                    flash('Data inserted!', category='success')  
                    return redirect(url_for('views.projectteam'))        

            if request.args.get("type_operation") == 'U':              
                cur.execute("UPDATE app.project_team SET st_user_leader  = " + st_user_leader +  ", user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "' where project_team_id = " + project_team_id)            
                flash('Data updated!', category='success')
                return redirect(url_for('views.projectteam'))

        cur=db.get_cursor()
        cur.execute("select ptm.project_team_id " +
                "     , prj.project_name " +
                "     , usr.first_name " +
                "     , case when ptm.st_user_leader = 1 then 'X' else '' end st_user_leader " +
                "from app.project prj " +
                "     , app.user usr " +
                "     , app.project_team ptm " +
                "where prj.project_id = ptm.project_id " +
                "  and usr.id = ptm.user_id " + 
                " order by prj.project_name asc, ptm.st_user_leader desc, usr.first_name asc")
        data = cur.fetchall()

        cur.close

        return render_template("projectteam.html", output_data = data, user=current_user)

    if request.method == 'GET':        
        project_team_id = request.args.get('project_team_id', '') 
        
        cur=db.get_cursor()
        cur.execute("SELECT id, first_name FROM app.user order by 2")
        data_user = cur.fetchall()
        
        cur.execute("SELECT project_id, project_name FROM app.project order by 2")
        data_project = cur.fetchall()

        if request.args.get('type_operation', '') == 'D':
            type_operation = 'Delete'
        elif request.args.get('type_operation', '') == 'U':
            type_operation = 'Update'
        else:
            type_operation = 'Add'

        project_name = [0]
        first_name = [0] 
        user_id = ''
        project_id = ''
        st_user_leader = [0]

        if project_team_id != '':
            cur.execute("select ptm.project_team_id " +
                        "     , prj.project_name " +
                        "     , usr.first_name " +
                        "     , ptm.st_user_leader " +
                        "     , ptm.user_id " +
                        "     , ptm.project_id " +
                        "from app.project prj " +
                        "     , app.user usr " +
                        "     , app.project_team ptm " +
                        "where prj.project_id = ptm.project_id " +
                        "  and usr.id = ptm.user_id " + 
                        "  and ptm.project_team_id = "+ project_team_id +"")        
            team_member_project_team_id = cur.fetchall()
            project_name = [team_member_project_team_id_item[1] for team_member_project_team_id_item in team_member_project_team_id]
            first_name = [team_member_project_team_id_item[2] for team_member_project_team_id_item in team_member_project_team_id]
            user_id = [team_member_project_team_id_item[4] for team_member_project_team_id_item in team_member_project_team_id]
            project_id = [team_member_project_team_id_item[5] for team_member_project_team_id_item in team_member_project_team_id]
            st_user_leader = [team_member_project_team_id_item[3] for team_member_project_team_id_item in team_member_project_team_id]
        
        cur.execute("select ptm.project_team_id " +
                    "     , prj.project_name " +
                    "     , usr.first_name " +
                    "     , ptm.st_user_leader " +
                    "from app.project prj " +
                    "     , app.user usr " +
                    "     , app.project_team ptm " +
                    "where prj.project_id = ptm.project_id " +
                    "  and usr.id = ptm.user_id ")
        data_team= cur.fetchall()            

        cur.close

        return render_template("projectteamdata.html", user=current_user
                                                     , project_team_id = project_team_id
                                                     , project_id = project_id
                                                     , user_id = user_id
                                                     , st_user_leader = st_user_leader[0]
                                                     , project_name = project_name[0]
                                                     , first_name = first_name[0]
                                                     , team_list = data_team
                                                     , project_list = data_project
                                                     , user_list = data_user
                                                     , type_operation = type_operation)         


@views.route('/caqdas', methods=['GET', 'POST'])
@login_required
def caqdas():

    cur=db.get_cursor()

    if request.method == 'POST': 
        caqdas_search = request.form.get('caqdas_search') #Gets the note from the HTML 
        if len(caqdas_search) < 1:            
            return redirect(url_for('views.caqdas'))
        else:
            cur.execute("select caqdas.caqdas_id " +
                    "     , caqdas.caqdas_name " +
                    "     , caqdas.code_export_type_file " +                    
                    "from app.caqdas caqdas " +                    
                    "where upper(caqdas.caqdas_name) like upper('%" + request.form.get("caqdas_search") + "%')" +
                    " order by caqdas.caqdas_name asc")
            data = cur.fetchall()
            cur.close
            return render_template("caqdas.html", output_data = data, user=current_user)        
    else:    
        cur.execute("select caqdas.caqdas_id " +
                    "     , caqdas.caqdas_name " +
                    "     , caqdas.code_export_type_file " +                    
                    "from app.caqdas caqdas " +                                        
                    " order by caqdas.caqdas_name asc")
        
        data = cur.fetchall()
        cur.close
        return render_template("caqdas.html", output_data = data, user=current_user)

@views.route('/caqdasdata', methods= ['GET', 'POST'])
def caqdasdata(): 

    if request.method == 'POST':   

        cur=db.get_cursor()

        caqdas_id = request.form.get("caqdas_id")
        caqdas_name = request.form.get("caqdas_name")
        code_export_type_file = request.form.get("code_export_type_file")

        if request.args.get('type_operation', '') == 'D':
            code_export_caqdas = [0]  
            code_export_caqdas_item = 0          
            cur.execute("SELECT count(0) FROM app.code_export where caqdas_id = " + caqdas_id)    
            code_export_caqdas = cur.fetchall()
            code_export_caqdas_item = [code_export_caqdas_item[0] for code_export_caqdas_item in code_export_caqdas]

            if int(code_export_caqdas_item[0]) > 0:  
                flash('There are codes exported using this CAQDAS!', category='error')
                return redirect(url_for('views.caqdas'))
            
            else:
                cur.execute("update app.caqdas set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where caqdas_id = " + caqdas_id)
                cur.execute("delete from app.caqdas where  caqdas_id = " + caqdas_id)            
                flash('Data deleted!', category='success')
                return redirect(url_for('views.caqdas'))

        if request.args.get('type_operation', '') == 'A':            
            cur.execute("insert into app.caqdas (caqdas_name, code_export_type_file, user_id_log, user_name_log) values ('" + caqdas_name + "', '" + code_export_type_file + "', " + current_user.get_id()  + ", '" + current_user.first_name  + "')")            
            flash('Data inserted!', category='success')
            return redirect(url_for('views.caqdas'))

        if request.args.get('type_operation', '') == 'U':
            cur.execute("update app.caqdas set caqdas_name = '" + caqdas_name + "', user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "' where caqdas_id = " + caqdas_id)
            flash('Data updated!', category='success')
            return redirect(url_for('views.caqdas'))
        
        cur.execute("SELECT * FROM app.caqdas order by caqdas_name")
        data = cur.fetchall()
        cur.close
        return render_template("caqdas.html", output_data = data, user=current_user)        

    if request.method == 'GET':              

        caqdas_id = request.args.get("caqdas_id")
        caqdas_name = request.args.get("caqdas_name")
        code_export_type_file = request.args.get("code_export_type_file")

        if request.args.get('type_operation', '') == 'D':
            type_operation = 'Delete'
        elif request.args.get('type_operation', '') == 'U':
            type_operation = 'Update'
        else:
            type_operation = 'Add'

        cur=db.get_cursor()
        cur.execute("select caqdas_id, caqdas_name from app.caqdas order by caqdas_name")
        data_caqdas_list = cur.fetchall()            

        cur.close

        return render_template("caqdasdata.html", user=current_user, caqdas_id = caqdas_id, caqdas_name = caqdas_name, code_export_type_file = code_export_type_file,  data_caqdas = data_caqdas_list, type_operation = type_operation)         


@views.route('/uploadonto', methods=['POST'])
def uploadfileonto():   
    if request.method == 'POST':   
        urlfile = request.form.get('urlfile')
        if urlfile !='':                    

            output_file = ".\\website\\onto\\homogenise.owl"
             
            with urllib.request.urlopen(urlfile) as response, open(output_file, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)

            flash('Ontology added successfully!', category='success')
        else:
            flash('Repeat operation and selecting a OWL file!', category='success')

        return render_template("uploadonto.html", user=current_user)         
