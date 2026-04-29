import os
import re
import types
import tempfile
import urllib.request
import shutil
import uuid
import json
import time
import requests as http_requests
from flask import Blueprint, redirect, render_template, request, flash, url_for, jsonify, current_app, Response
from owlready2 import get_ontology, Thing, ObjectProperty
from flask_login import login_required, current_user
from franz.openrdf.rio.rdfformat import RDFFormat
from wordcloud import WordCloud, STOPWORDS
import io
import base64
from website.settings import db
from werkzeug.security import generate_password_hash
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import chardet
from langchain_community.graphs import Neo4jGraph
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import tool
from langchain import hub
from website.features.synopsis.synopsis_repository import SynopsisRepository
from website.features.synopsis.triple_conversion import TripleConversion

views = Blueprint('views', __name__)


@views.route('/')
@login_required
def home():
    return render_template("home.html", user=current_user)

@views.route('/synopsis', methods=['GET', 'POST'])
@login_required
def generateText():
    if request.method == 'GET':
        cur = db.get_cursor()
        cur.execute("""
            SELECT 
                project.project_id, 
                project.project_name, 
                STRING_AGG(files.old_name, ', ') AS all_old_names 
            FROM 
                app.project AS project
            JOIN 
                app.project_file AS files 
            ON 
                files.project_id = project.project_id
            GROUP BY 
                project.project_id, project.project_name
        """) 
        data = cur.fetchall()
        cur.close()
        
        return render_template("synopsis.html", output_data=data, user=current_user)
    else:        
        project_id = request.form.get('project_id')

        repo = SynopsisRepository()
        individuals_by_object_property_results = repo.get_individuals_related_by_object_property(project_id)
        classes_by_superclass_results = repo.get_classes_related_by_superclasses(project_id)
        classes_by_domain_and_range_results = repo.get_classes_related_by_object_property_domains_and_ranges(project_id)

        triples = classes_by_superclass_results +  classes_by_domain_and_range_results + individuals_by_object_property_results

        converter = TripleConversion()
        paragraph = converter.triple_to_paragraph(triples).replace("subClassOf", "is")

        return render_template("synopsis.html", project_id=project_id, paragraph=paragraph, user=current_user)


def do_graph(project_id, selected_chart, selected_classes):
    word_list = []
    word_count = []
    formatted_values = ", ".join(f"'{word}'" for word in selected_classes)
    graph_sparql = f"""
                SELECT (REPLACE(STR(?class), "^.*/([^/]*)$", "$1") as ?localS) ?count
                WHERE 
                {{
                    {{
                        SELECT ?class (COUNT(?class) AS ?count) {{ ?resource a ?class }} GROUP BY ?class
                    }} .                                          
                    FILTER((REPLACE(STR(?class), "^.*/([^/]*)$", "$1")) IN ({formatted_values}))
                }} ORDER BY ?localS
            """  
    with db.get_allegro(project_id) as conn:
        with conn.executeTupleQuery(graph_sparql) as results:
            for result in results:
                name = str(result.getValue('localS')).replace('"', '')
                count = int(str(result.getValue('count')).split('^')[0].replace('"', ''))
                word_count.append([name, count])
                for _ in range(count):
                    word_list.append(name)
    b64 = ''
    stopwords = set(STOPWORDS)
    custom_stopwords = ["untitled", "ontology"]
    stopwords.update(custom_stopwords)
    if selected_chart == 'Word cloud':
        words = ' '.join(word_list) 
        cloud = WordCloud(stopwords=stopwords,width=1280, height=720, background_color='white', collocations=False).generate(words)
        buffer = io.BytesIO()
        cloud.to_image().save(buffer, 'png')
        b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
    elif selected_chart == 'Pie chart':
        counts = np.array([sublist[1] for sublist in word_count])
        labels = [sublist[0] for sublist in word_count]
        plt.pie(counts, labels=labels, autopct='%1.1f%%')
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300)
        b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
    elif selected_chart == 'Bar chart':
        x = np.array([sublist[0] for sublist in word_count])
        y = np.array([sublist[1] for sublist in word_count])
        plt.bar(x, y)
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300)
        b64 = base64.b64encode(buffer.getvalue()).decode('ascii')

    return b64

@views.route('/generatestatistics', methods=['GET', 'POST'])
def generatestatistics():

    is_knowledge_graph_selected = False
    graph_data = None
    project_id = request.args.get('project_id', '0') if request.method == 'GET' else request.form.get("project_id")
    cur = db.get_cursor()

    cur.execute("SELECT project_id, project_name FROM app.project order by 2")
    data_project = cur.fetchall()

    cur.close()
    chart_list = ['Word cloud', 'Pie chart', 'Bar chart', 'Knowledge graph']
    class_list = []
    with db.get_allegro(project_id) as conn:
        with conn.executeTupleQuery("""
                    SELECT DISTINCT (REPLACE(STR(?subject), "^.*/([^/]*)$", "$1") as ?s)
                    WHERE { 
                          ?subject ?p ?o . 
                          FILTER (!isBlank(?subject)) .
                          FILTER (!isBlank(?o)) .
                          FILTER(?p NOT IN (<http://semanticscience.org/resource/hasUnit>, rdfs:domain, rdfs:range, rdfs:subPropertyOf, rdf:first, rdf:rest, owl:members, <http://www.w3.org/ns/prov#generatedAtTime>, owl:allValuesFrom, <http://semanticscience.org/resource/isAttributeOf>)) .              
                          FILTER(str(?subject) != "") .
                    }
                """) as results:
            for result in results:
                uri = str(result.getValue('s')).replace('"', '')
                #class_name = uri.split('#')[1].split('>')[0]
                class_list.append(uri)

    class_list = sorted(class_list)

    if request.method == 'POST':
        try:
            selected_chart = request.form.get("chart_type")
            selected_classes = request.form.getlist("class_list")
            if project_id == 'null' or selected_chart == 'null' or len(selected_classes) == 0:
                flash('Fill out all data to execute transaction!', category='error')
                return redirect(request.url)

            b64 = ''
            if selected_chart in ['Word cloud', 'Pie chart', 'Bar chart']:
                b64 = do_graph(project_id, selected_chart, selected_classes)
            elif selected_chart == 'Knowledge graph':
                nodes_dict = {}
                edges = []
                is_knowledge_graph_selected = True
                formatted_values = ", ".join(f"'{word}'" for word in selected_classes)                
                sparql = f"""                                        
                    SELECT distinct
                        (STR(?s) as ?s_uri)
                        (REPLACE(STR(?s), "^.*/([^/]*)$", "$1") as ?s_name)
                        (REPLACE(STR(?p), "^.*/([^/]*)$", "$1") as ?label)
                        (STR(?o) as ?o_uri)
                        (REPLACE(STR(?o), "^.*/([^/]*)$", "$1") as ?o_name)
                        (REPLACE(STR(?s_type), "^.*[/#]([^/#]*)$", "$1") as ?s_type_name)
                        (REPLACE(STR(?o_type), "^.*[/#]([^/#]*)$", "$1") as ?o_type_name)
                    WHERE {{
                              ?s ?p ?o .
                              OPTIONAL {{ ?s rdf:type ?s_type }}
                              OPTIONAL {{ ?o rdf:type ?o_type }}
                              FILTER(?p NOT IN (<http://semanticscience.org/resource/hasUnit>, rdfs:domain, rdfs:range, rdfs:subPropertyOf, rdf:first, rdf:rest, owl:members, <http://www.w3.org/ns/prov#generatedAtTime>, owl:allValuesFrom, <http://semanticscience.org/resource/isAttributeOf>)) .
                              FILTER(?o NOT IN (owl:ObjectProperty, owl:Class, owl:NamedIndividual, owl:AllDisjointClasses, owl:Restriction, <http://semanticscience.org/resource/isAttributeOf>)) .
                              FILTER (!isBlank(?o)) . FILTER (!isBlank(?s)) . FILTER(?o != '') .
                              FILTER((REPLACE(STR(?s), "^.*/([^/]*)$", "$1")) IN ({formatted_values}))
                            }}                              
                   """
                with db.get_allegro(project_id) as conn:
                    with conn.executeTupleQuery(sparql) as results:
                        for result in results:
                            s_uri = str(result.getValue('s_uri')).replace('"', '')
                            s_name = str(result.getValue('s_name')).replace('"', '')
                            s_type = str(result.getValue('s_type_name')).replace('"', '')
                            label = str(result.getValue('label')).replace('"', '')
                            o_uri = str(result.getValue('o_uri')).replace('"', '')
                            o_name = str(result.getValue('o_name')).replace('"', '')
                            o_type = str(result.getValue('o_type_name')).replace('"', '')

                            nodes_dict[s_uri] = {"id": s_uri, "name": s_name, "type": s_type}
                            nodes_dict[o_uri] = {"id": o_uri, "name": o_name, "type": o_type}
                            edges.append({"source": s_uri, "target": o_uri, "label": label})

                graph_data = {"data":{
                    "nodes": list(nodes_dict.values()),
                    "edges": edges
                }}


            plt.clf()
        except Exception as e:
            flash(str(e), category='error')

        return render_template("generatestatistics.html", user=current_user
                               , project_id=int(project_id)
                               , project_list=data_project
                               , class_list=class_list
                               , selected_classes=selected_classes
                               , chart_list=chart_list
                               , chart_type=selected_chart
                               , img_uri=b64 if not is_knowledge_graph_selected else None
                               , is_knowledge_graph_selected=is_knowledge_graph_selected
                               , graph_data=graph_data if is_knowledge_graph_selected else None
                               )

    elif request.method == 'GET':
        return render_template("generatestatistics.html", user=current_user
                               , project_id=int(project_id)
                               , project_list=data_project
                               , class_list=class_list
                               , chart_list=chart_list                               
                               , img_uri='0')


@views.route('/analysis', methods=['GET', 'POST'])
@login_required
def analysis():
    if request.method == 'POST':
        text = request.form.get('analysis')
        if len(text) == 0:
            return jsonify({'message': 'Analysis can not be empty!'})

        project_id = request.form.get('project_id')
        chart_type = request.form.get('chart_type')
        selected_classes = request.form.get('selected_classes')

        cur = db.get_cursor()
        query = 'INSERT INTO app.analysis(project_id, selected_classes, chart_type, analysis, user_id_log, user_name_log) ' \
                'VALUES (%s, %s, %s, %s, %s, %s)'
        cur.execute(query, (project_id, selected_classes, chart_type, text, current_user.get_id(), current_user.first_name))
        cur.close()

        return jsonify({'message': 'Analysis submitted!'})
    else:
        project_id = request.args.get('project_id', '')
        cur = db.get_cursor()
        query = 'SELECT p.project_name, a.chart_type, a.selected_classes, a.analysis FROM app.analysis a '\
                'JOIN app.project p ON p.project_id = a.project_id WHERE a.project_id = %s'
        cur.execute(query, project_id)
        data = cur.fetchall()
        print(data)
        cur.close()
        return render_template("analysis.html", output_data=data, user=current_user)


@views.route('/insights', methods=['GET', 'POST'])
@login_required
def insights():
    cur = db.get_cursor()

    if request.method == 'POST':
        project_search = request.form.get('project_search')  # Gets the note from the HTML
        if len(project_search) < 1:
            return redirect(url_for('views.insights'))
        else:
            cur.execute("select project.project_id, project.project_name, count(files) from app.project project join app.project_file files on files.project_id = project.project_id where project.project_name like '%" + request.form.get("project_search") + "%' group by project.project_id")
            data = cur.fetchall()
            cur.close()
            return render_template("insights.html", output_data=data, user=current_user, last_search=request.form.get("project_search"))
    else:
        cur.execute("""
            SELECT 
                project.project_id, 
                project.project_name, 
                STRING_AGG(files.old_name, ', ') AS all_old_names
            FROM 
                app.project AS project
            JOIN 
                app.project_file AS files 
            ON 
                files.project_id = project.project_id
            GROUP BY 
                project.project_id, project.project_name
        """)
        data = cur.fetchall()
        cur.close()
        return render_template("insights.html", output_data=data, user=current_user)


@views.route('/insightsdata', methods=['GET', 'POST'])
def insightsdata():
    if request.method == 'POST':
        try:
            project_id = request.form.get("project_id")
            if project_id == 'null':
                flash('Fill out all data to execute transaction!', category='error')
                return redirect(request.url)

            if request.args.get("type_operation") is None:
                if 'file' not in request.files:
                    flash('You must select a file.', category='error')
                    return redirect(request.url)

            basedir = os.path.abspath(os.path.dirname(__file__))
            userfiles_dir = os.path.join(basedir, 'userfiles')
            os.makedirs(userfiles_dir, exist_ok=True)

            files = request.files.getlist('file')
            file_names = []
            for file in files:
                if file.filename != '':
                    file_bytes = file.read()
                    result = chardet.detect(file_bytes)
                    detected_encoding = result['encoding']
                    if detected_encoding is None:
                        flash('Could not read the files.', category='error')
                        return redirect(request.url)

                    try:
                        decoded_text = file_bytes.decode(detected_encoding)
                        file_id = str(uuid.uuid4())
                        path = os.path.join(userfiles_dir, file_id)

                        with open(path, 'w', encoding='utf-8') as f:
                            f.write(decoded_text)

                        file_names.append([file_id, file.filename])
                    except Exception as e:
                        flash('Error while saving file: ' + str(e), category='error')
                        return redirect(request.url)

            if len(file_names) == 0 and request.args.get("type_operation") is None:
                flash('You must select a file.', category='error')
                return redirect(request.url)

            cur = db.get_cursor()
            if request.args.get("type_operation") == 'D':
                project_id = request.args.get('project_id', '0')
                cur.execute("select file_name from app.project_file where project_id = " + project_id)
                file_names = cur.fetchall()
                for file_name in file_names:
                    path = os.path.join(userfiles_dir, file_name[0])
                    if os.path.exists(path):
                        os.remove(path)
                cur.execute("delete from app.project_file where project_id = " + project_id)
                with db.get_allegro(project_id) as conn:
                    conn.clear()
                flash('Data deleted!', category='success')
            else:
                if request.args.get("type_operation") == 'E':
                    project_id = request.args.get('project_id', '0')
                for file_name in file_names:
                    cur.execute("INSERT INTO app.project_file(project_file_id, project_id, file_name, old_name, user_id_log, user_name_log) VALUES (nextval('app.project_file_project_file_id_seq'), " + project_id + ", '" + file_name[0] + "', '" + file_name[1] + "', " + current_user.get_id() + ", '" + current_user.first_name + "')")
                    with db.get_allegro(project_id) as conn:
                        path = os.path.join(userfiles_dir, file_name[0])
                        conn.addFile(path, None, format=RDFFormat.TURTLE)
                flash('Data inserted!', category='success')
        except Exception as e:
            flash(str(e), category='error')

        return redirect(url_for('views.insights'))

    elif request.method == 'GET':
        try:
            operation = request.args.get('type_operation', '')
            if operation == 'D':
                type_operation = 'Delete'
            elif operation == 'E':
                type_operation = 'Edit'
            else:
                type_operation = 'Add'

            project_id = request.args.get('project_id', '0')
            cur = db.get_cursor()

            file_to_remove = request.args.get('remove_file', '')
            if len(file_to_remove) > 0:
                cur.execute("select file_name from app.project_file where project_id = " + project_id + " and old_name = '" + file_to_remove + "'")
                file_names = cur.fetchall()
                basedir = os.path.abspath(os.path.dirname(__file__))
                userfiles_dir = os.path.join(basedir, 'userfiles')
                for file_name in file_names:
                    path = os.path.join(userfiles_dir, file_name[0])
                    if os.path.exists(path):
                        os.remove(path)
                cur.execute("delete from app.project_file where project_id = " + project_id + " and old_name = '" + file_to_remove + "'")
                with db.get_allegro(project_id) as conn:
                    conn.clear()

                cur.execute('select files.file_name from app.project_file files where files.project_id = ' + project_id)
                file_names = cur.fetchall()
                with db.get_allegro(project_id) as conn:
                    for file in file_names:
                        path = os.path.join(userfiles_dir, file[0])
                        conn.addFile(path, None, format=RDFFormat.TURTLE)

                flash('File removed!', category='success')

            cur.execute('select files.old_name from app.project_file files where files.project_id = ' + project_id)
            file_names = cur.fetchall()

            cur.execute("SELECT project_id, project_name FROM app.project order by 2")
            data_project = cur.fetchall()

            cur.close()
        except Exception as e:
            flash(str(e), category='error')

        return render_template("insightsdata.html", user=current_user
                               , project_id=int(project_id)
                               , type_operation=type_operation
                               , file_names=file_names
                               , project_list=data_project)

@views.route('/rag', methods=['GET', 'POST'])
def rag():
    """Show list of projects and action 'Ask Graph' for each project.

    Clicking Ask Graph should open the loader page where the user provides the OpenAI
    token and can load the project's TTL into Neo4j and then ask questions.
    """
    cur = db.get_cursor()
    # reuse the same query used elsewhere to list projects and their file names
    cur.execute("""
            SELECT 
                project.project_id, 
                project.project_name, 
                STRING_AGG(files.old_name, ', ') AS all_old_names 
            FROM 
                app.project AS project
            JOIN 
                app.project_file AS files 
            ON 
                files.project_id = project.project_id
            GROUP BY 
                project.project_id, project.project_name
        """)
    data = cur.fetchall()
    cur.close()

    return render_template('rag_projects.html', output_data=data, user=current_user)


@views.route('/rag/load', methods=['GET', 'POST'])
@login_required
def rag_load():
    """Page to accept OpenAI token, load the project's TTL into Neo4j and allow QA.

    - GET: show token input and Load button for selected project
    - POST with action=load_graph: load TTL into Neo4j (clear DB and index first), create embeddings and vector index
    - POST with action=ask: run the QA agent against the graph using provided token
    """
    project_id = request.args.get('project_id') if request.method == 'GET' else request.form.get('project_id')
    if not project_id:
        flash('Project id not provided.', category='error')
        return redirect(url_for('views.rag'))

    resposta_rag = ''
    graph_loaded = False
    token_prefill = ''

    if request.method == 'POST':
        action = request.form.get('action')
        token = request.form.get('openai_token', '').strip()

        # Resolve project's ttl file path from DB
        cur = db.get_cursor()
        cur.execute('select file_name from app.project_file where project_id = %s limit 1', (project_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            flash('No file registered for this project.', category='error')
            return redirect(url_for('views.rag'))

        # path where files are stored inside the website package
        basedir = os.path.abspath(os.path.dirname(__file__))
        userfiles_dir = os.path.join(basedir, 'userfiles')
        file_name_on_disk = row[0]
        src_path = os.path.join(userfiles_dir, file_name_on_disk)
        if not os.path.exists(src_path):
            flash('Project file not found on disk: ' + src_path, category='error')
            return redirect(url_for('views.rag'))

        if action == 'load_graph':
            if not token:
                flash('OpenAI token is required to create embeddings.', category='error')
                return redirect(url_for('views.rag_load', project_id=project_id))

            try:
                # prepare import file inside import/ and point Neo4j to /var/lib/neo4j/import
                neo4j_import_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../import'))
                os.makedirs(neo4j_import_dir, exist_ok=True)
                file_id = str(uuid.uuid4())
                dest_filename = f"{file_id}.ttl"
                dest_path = os.path.join(neo4j_import_dir, dest_filename)
                shutil.copy(src_path, dest_path)
                neo4j_internal_path = f"/var/lib/neo4j/import/{dest_filename}"

                # connect to neo4j
                NEO4J_URI = "bolt://neo4j-rag:7687"
                NEO4J_USERNAME = "neo4j"
                NEO4J_PASSWORD = "sua_senha_segura"

                graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD)

                # clear graph and index if exist
                try:
                    graph.query("DROP INDEX rag_index IF EXISTS")
                except Exception:
                    pass
                try:
                    graph.query("MATCH (n) DETACH DELETE n")
                except Exception:
                    # continue even if delete fails
                    pass

                # init n10s and import
                try:
                    graph.query("CREATE CONSTRAINT n10s_unique_uri FOR (r:Resource) REQUIRE r.uri IS UNIQUE")
                except Exception as e:
                    if "already exists" not in str(e):
                        raise
                graph.query("CALL n10s.graphconfig.init()")
                graph.query(f"CALL n10s.rdf.import.fetch('file://{neo4j_internal_path}', 'Turtle')")

                # create embeddings for nodes
                embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=token)
                node_text_query = """
                MATCH (n)
                WHERE n.ns2__hasValue IS NOT NULL
                RETURN n.uri AS node_id, n.ns2__hasValue AS text
                """
                node_texts = graph.query(node_text_query)
                for node in node_texts:
                    node_id = node.get('node_id')
                    text_value = node.get('text')
                    if isinstance(text_value, list):
                        final_text = " ".join(str(item) for item in text_value if item)
                    else:
                        final_text = str(text_value)
                    if final_text.strip():
                        embedding = embeddings.embed_query(final_text)
                        graph.query("MATCH (n {uri: $node_id}) SET n.embedding = $embedding",
                                    params={"node_id": node_id, "embedding": embedding})

                # create vector index
                graph.query("""
                CREATE VECTOR INDEX rag_index IF NOT EXISTS
                FOR (n:Resource) ON (n.embedding)
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 1536,
                    `vector.similarity_function`: 'cosine'
                }}
                """)

                graph_loaded = True
                token_prefill = token
                flash('Graph loaded into Neo4j, embeddings created and vector index configured!', category='success')

            except Exception as e:
                flash('Error loading graph: ' + str(e), category='error')
                # cleanup copied file
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                except Exception:
                    pass

        elif action == 'ask':
            # ask question using provided token
            pergunta = request.form.get('pergunta', '')
            if not token:
                flash('OpenAI token is required to ask questions.', category='error')
                return redirect(url_for('views.rag_load', project_id=project_id))

            try:
                NEO4J_URI = "bolt://neo4j-rag:7687"
                NEO4J_USERNAME = "neo4j"
                NEO4J_PASSWORD = "sua_senha_segura"

                graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD)

                llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0, openai_api_key=token, max_tokens=32768)
                embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=token)

                # tools
                @tool
                def vector_search_start_node(question: str) -> list[dict]:
                    """Finds the most relevant starting nodes for a question using vector search.

                    Returns a list of dicts with keys: uri, label, score.
                    """
                    pergunta_embedding = embeddings.embed_query(question)
                    query = """
                    CALL db.index.vector.queryNodes('rag_index', $top_k, $embedding) YIELD node, score
                    RETURN node.uri AS uri, node.ns2__hasValue AS label, score
                    LIMIT $top_k
                    """
                    result = graph.query(query, params={"embedding": pergunta_embedding, "top_k": 20})
                    for item in result:
                        if isinstance(item.get('label'), list):
                            item['label'] = " | ".join(item['label'])
                    return result

                @tool
                def list_neighbors(node_uri: str) -> list[dict]:
                    """Return direct neighbor nodes and relationship types for a given node URI.

                    Returns list of dicts with keys: relationship_type, neighbor_uri, neighbor_label.
                    """
                    query = """
                    MATCH (n {uri: $uri})-[r]-(m)
                    RETURN type(r) AS relationship_type, m.uri AS neighbor_uri, m.ns2__hasValue AS neighbor_label
                    """
                    result = graph.query(query, params={"uri": node_uri})
                    for item in result:
                        if isinstance(item.get('neighbor_label'), list):
                            item['neighbor_label'] = " | ".join(item['neighbor_label'])
                    return result

                @tool
                def get_node_details(node_uri: str) -> dict:
                    """Return all non-embedding properties for the node identified by URI.

                    Returns a dict of property->value (lists joined into strings), excluding 'embedding'.
                    """
                    query = "MATCH (n {uri: $uri}) RETURN properties(n) AS details"
                    result = graph.query(query, params={"uri": node_uri})
                    if not result:
                        return {}
                    details = result[0].get('details', {})
                    cleaned = {}
                    for key, value in details.items():
                        if isinstance(value, list) and key != 'embedding':
                            cleaned[key] = ", ".join(map(str, value))
                        elif key != 'embedding':
                            cleaned[key] = value
                    return cleaned

                tools = [vector_search_start_node, list_neighbors, get_node_details]
                prompt = hub.pull("hwchase17/react")
                custom_prompt = """
            You are an expert in querying an ontology stored in a Neo4j graph.
            Your role is to answer user questions using the graph as a knowledge source, exploring nodes and relationships.

            You have access to the following tools:

            1. vector_search_start_node
            - Use this tool to find the most relevant starting nodes for the user's question using vector search.

            2. list_neighbors
            - Use this tool to expand related concepts of a specific node.
            - Use when you need to explore nodes connected to the current node.

            3. get_node_details
            - Use this tool to get all detailed properties of a specific node, such as descriptions or attributes.
            - Use when the user asks for more details about a concept.

            Important rules:
            - Whenever the user asks an initial question, always start by using `vector_search_start_node`.
            - If you need to explore related concepts, use `list_neighbors`.
            - If the user asks for more information about a specific node, use `get_node_details`.
            - Combine the results from the tools with your reasoning to provide a clear answer in English.
            - Respond in a didactic and structured way, avoiding just listing raw data. Explain what was found and how it relates to the question.

            Response format:
            - Explain your reasoning in natural language.
            - Mention the concepts found in the graph.
            - Only use tools when necessary; if you already have enough information, answer directly.
            """
                agent = create_react_agent(llm, tools, prompt=prompt + custom_prompt)
                agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)

                resposta = agent_executor.invoke({"input": pergunta})
                resposta_rag = resposta.get('output', '')
                token_prefill = token
                # keep the ask form visible after asking so user can ask more questions
                graph_loaded = True

            except Exception as e:
                flash('Error answering question: ' + str(e), category='error')

    # GET or after POST; show form. Keep token only in page's form fields (not saved in DB)
    return render_template('rag_load.html', user=current_user, project_id=project_id, resposta_rag=resposta_rag, graph_loaded=graph_loaded, openai_token_prefill=token_prefill)


@views.route('/projectteam', methods=['GET', 'POST'])
@login_required
def projectteam():

    cur = db.get_cursor()

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
            cur.close()
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
        cur.close()
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
            cur.close()
            return render_template("modifyuser.html", output_data = data, user=current_user)
        else:
            cur.execute("select id, first_name, email, user_type_id from app.user  where upper(first_name) like upper('%" + request.form.get('username_search') + "%') order by first_name")
            data = cur.fetchall()
            cur.close()
            return render_template("modifyuser.html", output_data = data, user=current_user)
    else:
        cur.execute("select id, first_name, email, user_type_id from app.user order by first_name")
        data = cur.fetchall()
        cur.close()
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
            cur.close()
            return render_template("usertype.html", output_data = data, user=current_user)
        else:
            cur=db.get_cursor()
            cur.execute("SELECT * FROM app.user_type where upper(user_type_name) like upper('%" + request.form.get("usertype_search") + "%') order by user_type_name")
            data = cur.fetchall()
            cur.close()
            return render_template("usertype.html", output_data = data, user=current_user)

    else:
        cur=db.get_cursor()
        cur.execute("SELECT * FROM app.user_type order by user_type_name")
        data = cur.fetchall()

        cur.close()

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
            cur.close()
            return render_template("researchline.html", output_data = data, user=current_user)
        else:
            cur=db.get_cursor()
            cur.execute("SELECT * FROM app.research_line where upper(research_line_name) like upper('%" + request.form.get("researchline_search") + "%') order by research_line_name")
            data = cur.fetchall()
            cur.close()
            return render_template("researchline.html", output_data = data, user=current_user)
    else:

        cur = db.get_cursor()
        cur.execute("SELECT * FROM app.research_line order by research_line_name")
        data = cur.fetchall()

        cur.close()

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
                cur.close()
                return redirect(url_for('views.usertype'))

            else:
                cur.execute("update app.user_type set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where user_type_id = " + user_type_id)
                cur.execute("delete from app.user_type where user_type_id = " + user_type_id)
                cur.close()
                flash('Data deleted!', category='success')
                return redirect(url_for('views.usertype'))

        if request.args.get('type_operation', '') == 'A':
            cur.execute("insert into app.user_type (user_type_id, user_type_name, user_id_log, user_name_log) values (nextval('app.user_type_user_type_id_seq'), '" + user_type_name + "', " + current_user.get_id()  + ", '" + current_user.first_name  + "')")
            cur.close()
            flash('Data inserted!', category='success')
            return redirect(url_for('views.usertype'))

        if request.args.get('type_operation', '') == 'U':
            cur.execute("update app.user_type set user_type_name = '" + user_type_name + "', user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where user_type_id = " + user_type_id)
            cur.close()
            flash('Data updated!', category='success')
            return redirect(url_for('views.usertype'))

        cur.close()
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

        cur = db.get_cursor()
        cur.execute("select user_type_id, user_type_name from app.user_type order by user_type_name")
        data_user_type = cur.fetchall()

        cur.close()

        return render_template("usertypedata.html", user=current_user, user_type_id = user_type_id, user_type_name = user_type_name,  usertype_list = data_user_type, type_operation = type_operation)


@views.route('/researchlinedata', methods= ['GET', 'POST'])
def researchlinedata():

    if request.method == 'POST':

        cur = db.get_cursor()

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
                cur.close()
                return redirect(url_for('views.researchline'))

            else:
                cur.execute("update app.research_line set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where research_line_id = " + research_line_id)
                cur.execute("delete from app.research_line where research_line_id = " + research_line_id)
                cur.close()
                flash('Data deleted!', category='success')
                return redirect(url_for('views.researchline'))

        if request.args.get('type_operation', '') == 'A':
            cur.execute("insert into app.research_line (research_line_name, user_id_log, user_name_log) values ('" + research_line_name + "', " + current_user.get_id()  + ", '" + current_user.first_name  + "')")
            cur.close()
            flash('Data inserted!', category='success')
            return redirect(url_for('views.researchline'))

        if request.args.get('type_operation', '') == 'U':
            cur.execute("update app.research_line set research_line_name = '" + research_line_name + "', user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "' where research_line_id = " + research_line_id)
            cur.close()
            flash('Data updated!', category='success')
            return redirect(url_for('views.researchline'))

        cur.execute("SELECT * FROM app.research_line order by research_line_name")
        data = cur.fetchall()
        cur.close()
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

        cur = db.get_cursor()
        cur.execute("select research_line_id, research_line_name from app.research_line order by research_line_name")
        data_research_line = cur.fetchall()

        cur.close()

        return render_template("researchlinedata.html", user=current_user, research_line_id = research_line_id, research_line_name = research_line_name,  researchline_list = data_research_line, type_operation = type_operation)

@views.route('/projectresearch', methods=['GET', 'POST'])
@login_required
def projectresearch():
    if request.method == 'POST':
        project_search = request.form.get('project_search') #Gets the note from the HTML
        if len(project_search) < 1:
            cur = db.get_cursor()
            cur.execute("SELECT * FROM app.project order by project_name")
            data = cur.fetchall()
            cur.close()
            return render_template("projectresearch.html", output_data = data, user=current_user)
        else:
            cur=db.get_cursor()
            cur.execute("SELECT * FROM app.project where upper(project_name) like upper('%" + request.form.get("project_search") + "%') order by project_name")
            data = cur.fetchall()
            cur.close()
            return render_template("projectresearch.html", output_data = data, user=current_user)
    else:
        cur = db.get_cursor()
        cur.execute("SELECT * FROM app.project order by project_name")
        data = cur.fetchall()
        cur.close()

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
                    cur.close()
                    return redirect(url_for('views.projectresearch'))
                else:
                    cur.execute("update app.project set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where project_id = " + project_id)
                    cur.execute("delete from app.project where project_id = " + project_id)
                    cur.close()
                    flash('Data deleted!', category='success')
                    return redirect(url_for('views.projectresearch'))

            if request.args.get('type_operation', '') == 'A':
                cur.execute("insert into app.project (project_id, project_name, project_description, research_line_id, user_id_log, user_name_log) values (nextval('app.project_project_id_seq'), '" + project_name + "', '" + project_description +  "' , " + research_line_id + ", " + current_user.get_id()  + ", '" + current_user.first_name  + "')")
                cur.close()
                flash('Data inserted!', category='success')
                return redirect(url_for('views.projectresearch'))

            if request.args.get('type_operation', '') == 'U':
                cur.execute("update app.project set project_name = '" + project_name + "', project_description = '" + project_description + "' , research_line_id = " + research_line_id + ", user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "' where project_id = " + project_id)
                cur.close()
                flash('Data updated!', category='success')
                return redirect(url_for('views.projectresearch'))

        cur.execute("SELECT * FROM app.project order by project_name")
        data = cur.fetchall()
        cur.close()
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
        data_research_line = cur.fetchall()

        cur.close()

        return render_template("projectdata.html", user=current_user, project_id = project_id, project_name = project_name, project_description = project_description, researchline_name = research_line_name[0], researchline_list = data_research_line, type_operation = type_operation)

@views.route('/modifyuserdata', methods= ['GET', 'POST'])
def modifyuserdata():

    if request.method == 'POST':
        user_id = request.form.get('user_id', '')
        user_type_id = request.form.get("user_type_id")
        first_name = request.form.get("first_name")
        password1 = request.form.get("password1")
        password2 = request.form.get("password2")

        cur = db.get_cursor()

        if request.args.get('type_operation', '') == 'D':

            project_team = [0]
            project_team_item = 0
            cur.execute("SELECT count(0) FROM app.project_team where user_id = " + user_id)
            project_team = cur.fetchall()
            project_team_item = [project_team_item_item[0] for project_team_item_item in project_team]

            if int(project_team_item[0]) > 0:
                flash('There are project teams using this user!', category='error')
                cur.close()
                return redirect(url_for('views.modifyuser'))

            else:
                cur.execute("update app.user set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where id = " + user_id)
                cur.execute("delete from app.user where id = " + user_id)
                cur.close()
                flash('Data deleted!', category='success')
                return redirect(url_for('views.modifyuser'))

        if request.args.get('type_operation', '') == 'U':

            if password1 != password2:
                flash('Passwords don\'t match.', category='error')
                cur.close()
                return redirect(url_for('views.modifyuser'))

            elif len(password1) < 7:
                flash('Password must be at least 7 characters.', category='error')
                cur.close()
                return redirect(url_for('views.modifyuser'))

            else:
                cur.execute("update app.user set first_name = '" + first_name + "', user_type_id = " + user_type_id + ", password = '" + generate_password_hash(
                password1, method='pbkdf2:sha256') + "', user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where id = " + user_id)
                flash('Data updated!', category='success')
                cur.close()
                return redirect(url_for('views.modifyuser'))

        cur = db.get_cursor()
        cur.execute("select id, first_name, email, user_type_id from app.user order by first_name")
        data = cur.fetchall()

        cur.close()

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

        cur = db.get_cursor()
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
        data_user_type = cur.fetchall()

        cur.close()

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

        cur = db.get_cursor()

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
            cur.close()
            return redirect(url_for('views.projectteam'))

        else:
            if request.args.get("type_operation") == 'D':
                cur.execute("update app.project_team set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where project_team_id = " + project_team_id)
                cur.execute("delete from app.project_team where project_team_id = " + project_team_id)
                cur.close()
                flash('Data deleted!', category='success')
                return redirect(url_for('views.projectteam'))

            if request.args.get("type_operation") == 'A':

                if int(project_team_item[0]) > 0:
                    cur.close()
                    flash('Already there is a project for this user!', category='error')
                    return redirect(url_for('views.projectteam'))

                else:
                    cur.execute("INSERT INTO app.project_team(project_team_id, project_id, user_id, st_user_leader, user_id_log, user_name_log)	VALUES (nextval('app.project_team_project_team_id_seq'), " + project_id + ", " + user_id + ", " + st_user_leader + ", " + current_user.get_id()  + ", '" + current_user.first_name  + "')")
                    cur.close()
                    flash('Data inserted!', category='success')
                    return redirect(url_for('views.projectteam'))

            if request.args.get("type_operation") == 'U':
                cur.execute("UPDATE app.project_team SET st_user_leader  = " + st_user_leader +  ", user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "' where project_team_id = " + project_team_id)
                cur.close()
                flash('Data updated!', category='success')
                return redirect(url_for('views.projectteam'))

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

        cur.close()

        return render_template("projectteam.html", output_data = data, user=current_user)

    if request.method == 'GET':
        project_team_id = request.args.get('project_team_id', '')

        cur = db.get_cursor()
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
        data_team = cur.fetchall()

        cur.close()

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

    cur = db.get_cursor()

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
            cur.close()
            return render_template("caqdas.html", output_data = data, user=current_user)
    else:
        cur.execute("select caqdas.caqdas_id " +
                    "     , caqdas.caqdas_name " +
                    "     , caqdas.code_export_type_file " +
                    "from app.caqdas caqdas " +
                    " order by caqdas.caqdas_name asc")

        data = cur.fetchall()
        cur.close()
        return render_template("caqdas.html", output_data = data, user=current_user)

@views.route('/caqdasdata', methods= ['GET', 'POST'])
def caqdasdata():

    if request.method == 'POST':

        cur = db.get_cursor()

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
                cur.close()
                return redirect(url_for('views.caqdas'))

            else:
                cur.execute("update app.caqdas set user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "'  where caqdas_id = " + caqdas_id)
                cur.execute("delete from app.caqdas where  caqdas_id = " + caqdas_id)
                cur.close()
                flash('Data deleted!', category='success')
                return redirect(url_for('views.caqdas'))

        if request.args.get('type_operation', '') == 'A':
            cur.execute("insert into app.caqdas (caqdas_name, code_export_type_file, user_id_log, user_name_log) values ('" + caqdas_name + "', '" + code_export_type_file + "', " + current_user.get_id()  + ", '" + current_user.first_name  + "')")
            cur.close()
            flash('Data inserted!', category='success')
            return redirect(url_for('views.caqdas'))

        if request.args.get('type_operation', '') == 'U':
            cur.execute("update app.caqdas set caqdas_name = '" + caqdas_name + "', user_id_log = " + current_user.get_id()  + ", user_name_log = '" + current_user.first_name  + "' where caqdas_id = " + caqdas_id)
            cur.close()
            flash('Data updated!', category='success')
            return redirect(url_for('views.caqdas'))

        cur.execute("SELECT * FROM app.caqdas order by caqdas_name")
        data = cur.fetchall()
        cur.close()
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

        cur = db.get_cursor()
        cur.execute("select caqdas_id, caqdas_name from app.caqdas order by caqdas_name")
        data_caqdas_list = cur.fetchall()

        cur.close()

        return render_template("caqdasdata.html", user=current_user, caqdas_id = caqdas_id, caqdas_name = caqdas_name, code_export_type_file = code_export_type_file,  data_caqdas = data_caqdas_list, type_operation = type_operation)


@views.route('/uploadonto', methods=['POST'])
def uploadfileonto():
    if request.method == 'POST':
        urlfile = request.form.get('urlfile')
        if urlfile != '':

            output_file = ".\\website\\onto\\homogenise.owl"

            with urllib.request.urlopen(urlfile) as response, open(output_file, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)

            flash('Ontology added successfully!', category='success')
        else:
            flash('Repeat operation and selecting a OWL file!', category='success')

        return render_template("uploadonto.html", user=current_user)


@views.route('/aletheia', methods=['GET'])
@login_required
def aletheia():
    project_id = request.args.get('project_id', type=int)

    cur = db.get_cursor()
    cur.execute("SELECT project_id, project_name FROM app.project ORDER BY project_name")
    projects = cur.fetchall()
    cur.close()

    project_name = next((p[1] for p in projects if p[0] == project_id), None)

    return render_template("aletheia.html", user=current_user,
                           project_id=project_id,
                           project_name=project_name,
                           projects=projects)


@views.route('/api/graph', methods=['GET'])
@login_required
def api_graph():
    project_id = request.args.get('project_id', type=int)
    if not project_id:
        return jsonify({"ok": False, "error": "project_id is required"}), 400

    nodes_dict = {}
    edges = []

    sparql = """
        SELECT distinct
            (STR(?s) as ?s_uri)
            (REPLACE(STR(?s), "^.*/([^/]*)$", "$1") as ?s_name)
            (REPLACE(STR(?p), "^.*/([^/]*)$", "$1") as ?label)
            (STR(?o) as ?o_uri)
            (REPLACE(STR(?o), "^.*/([^/]*)$", "$1") as ?o_name)
            (REPLACE(STR(?s_type), "^.*[/#]([^/#]*)$", "$1") as ?s_type_name)
            (REPLACE(STR(?o_type), "^.*[/#]([^/#]*)$", "$1") as ?o_type_name)
        WHERE {
            ?s rdf:type ?s_type .
            ?o rdf:type ?o_type .
            ?s ?p ?o .
            FILTER(?s_type IN (owl:Class)) .
            FILTER(?o_type IN (owl:Class)) .
            FILTER(?p NOT IN (rdf:type, <http://semanticscience.org/resource/hasUnit>, rdfs:domain, rdfs:range, rdfs:subPropertyOf, rdf:first, rdf:rest, owl:members, <http://www.w3.org/ns/prov#generatedAtTime>, owl:allValuesFrom, <http://semanticscience.org/resource/isAttributeOf>)) .
            FILTER (!isBlank(?o)) . FILTER (!isBlank(?s)) .
        }
    """

    try:
        with db.get_allegro(project_id) as conn:
            with conn.executeTupleQuery(sparql) as results:
                for result in results:
                    s_uri  = str(result.getValue('s_uri')).replace('"', '')
                    s_name = str(result.getValue('s_name')).replace('"', '')
                    s_type = str(result.getValue('s_type_name')).replace('"', '')
                    label  = str(result.getValue('label')).replace('"', '')
                    o_uri  = str(result.getValue('o_uri')).replace('"', '')
                    o_name = str(result.getValue('o_name')).replace('"', '')
                    o_type = str(result.getValue('o_type_name')).replace('"', '')

                    nodes_dict[s_uri] = {"id": s_uri, "name": s_name, "type": s_type}
                    nodes_dict[o_uri] = {"id": o_uri, "name": o_name, "type": o_type}
                    edges.append({"source": s_uri, "target": o_uri, "label": label})

        return jsonify({"ok": True, "data": {"nodes": list(nodes_dict.values()), "edges": edges}})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _sanitize_owl_name(name: str) -> str:
    sanitized = re.sub(r'[^\w]', '_', name)
    if sanitized and sanitized[0].isdigit():
        sanitized = '_' + sanitized
    sanitized = re.sub(r'_+', '_', sanitized).rstrip('_')
    return sanitized or 'UnnamedClass'


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\-.]', '_', name) or 'ontology'


@views.route('/api/export/owl', methods=['POST'])
@login_required
def export_owl():
    data     = request.json
    nodes    = data.get('nodes', [])
    edges    = data.get('edges', [])
    iri      = data.get('iri',  'http://homogenise.example.org/ontology#')
    ont_name = data.get('name', 'ontology')

    onto = get_ontology(iri)

    with onto:
        classes = {}
        for node in nodes:
            cls = types.new_class(_sanitize_owl_name(node['name']), (Thing,))
            classes[node['id']] = cls

        properties = {}
        for edge in edges:
            label = edge.get('label', '')
            if label and label != 'subClassOf' and label not in properties:
                properties[label] = types.new_class(_sanitize_owl_name(label), (ObjectProperty,))

        for edge in edges:
            src_id = edge['source']['id'] if isinstance(edge['source'], dict) else edge['source']
            tgt_id = edge['target']['id'] if isinstance(edge['target'], dict) else edge['target']
            label  = edge.get('label', '')

            src = classes.get(src_id)
            tgt = classes.get(tgt_id)
            if not src or not tgt:
                continue

            if label == 'subClassOf':
                if tgt not in src.is_a:
                    src.is_a.append(tgt)
            elif label in properties:
                restriction = properties[label].some(tgt)
                if restriction not in src.is_a:
                    src.is_a.append(restriction)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.owl', delete=False) as f:
            tmp_path = f.name
        onto.save(file=tmp_path, format="rdfxml")
        with open(tmp_path, 'rb') as f:
            owl_content = f.read()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return Response(
        owl_content,
        mimetype='application/rdf+xml',
        headers={'Content-Disposition': f'attachment; filename="{_sanitize_filename(ont_name)}.owl"'}
    )


# ── Ollama helpers ────────────────────────────────────────────────────────

_OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')


def _to_pascal(name: str) -> str:
    replacements = {
        'á':'a','à':'a','ã':'a','â':'a','ä':'a',
        'é':'e','ê':'e','ë':'e',
        'í':'i','î':'i','ï':'i',
        'ó':'o','ô':'o','õ':'o','ö':'o',
        'ú':'u','û':'u','ü':'u',
        'ç':'c','ñ':'n',
        'Á':'A','À':'A','Ã':'A','Â':'A',
        'É':'E','Ê':'E',
        'Í':'I','Î':'I',
        'Ó':'O','Ô':'O','Õ':'O',
        'Ú':'U','Û':'U',
        'Ç':'C','Ñ':'N',
    }
    for k, v in replacements.items():
        name = name.replace(k, v)
    if name.isupper():
        name = name.capitalize()
    return name


def _process_suggestion(suggestions):
    actions = []
    for s in suggestions:
        action = {"type": s["action"], "payload": {}, "reason": s.get("reason", "")}
        if s["action"] in ("removeEdge", "createEdge"):
            action["payload"] = {"source": s["source"], "target": s["target"], "label": s.get("label", "")}
        elif s["action"] in ("createNode", "removeNode"):
            action["payload"] = {"id": s.get("id") or s.get("name"), "label": s.get("label") or s.get("name", "")}
        actions.append(action)
    return actions


# ── /api/suggest ──────────────────────────────────────────────────────────

@views.route('/api/suggest', methods=['POST'])
@login_required
def api_suggest():
    graph_data = request.get_json()
    if not graph_data:
        return jsonify({"ok": False, "error": "JSON ausente no corpo"}), 400

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    node_types = [{"name": n["name"], "type": n["type"]} for n in nodes]
    id_to_name = {n["id"]: n["name"] for n in nodes}
    edge_tuples = [
        {"source_name": id_to_name.get(e["source"], e["source"]),
         "target_name": id_to_name.get(e["target"], e["target"]),
         "label": e["label"]}
        for e in edges
    ]

    schema = {
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "enum": ["add_node", "remove_node", "add_edge", "remove_edge"]},
                        "node": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string", "enum": ["Class", "ObjectProperty"]}
                            },
                            "required": ["name"],
                            "additionalProperties": False
                        },
                        "edge": {
                            "type": "object",
                            "properties": {
                                "source_name": {"type": "string"},
                                "target_name": {"type": "string"},
                                "label": {"type": "string", "enum": ["subClassOf", "domain", "range"]}
                            },
                            "required": ["source_name", "target_name", "label"],
                            "additionalProperties": False
                        },
                        "reason": {"type": "string"}
                    },
                    "required": ["op", "reason"],
                    "additionalProperties": False
                }
            },
            "warnings": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["operations", "warnings"],
        "additionalProperties": False
    }

    messages = [
        {
            "role": "system",
            "content": "Você é um especialista em ontologias OWL.\nResponda APENAS com JSON válido. Não escreva markdown. Não escreva nada fora do JSON.\nEscreva todos os campos \"reason\" em português."
        },
        {
            "role": "user",
            "content": f"""Analise este grafo OWL e proponha um patch mínimo, útil e coerente.

NÓS ATUAIS:
{json.dumps(node_types, ensure_ascii=False, indent=2)}

ARESTAS ATUAIS:
{json.dumps(edge_tuples, ensure_ascii=False, indent=2)}

Responda EXATAMENTE neste formato, sem exceções:
{{
  "operations": [
    {{"op": "add_node", "node": {{"name": "NomeDaClasse", "type": "Class"}}, "reason": "motivo breve"}},
    {{"op": "remove_node", "node": {{"name": "NomeDoNo"}}, "reason": "motivo breve"}},
    {{"op": "add_edge", "edge": {{"source_name": "NoOrigem", "target_name": "NoDestino", "label": "subClassOf"}}, "reason": "motivo breve"}},
    {{"op": "remove_edge", "edge": {{"source_name": "NoOrigem", "target_name": "NoDestino", "label": "range"}}, "reason": "motivo breve"}}
  ],
  "warnings": []
}}

REGRAS:
- add_node/remove_node: SEMPRE inclua "node" com ao menos "name"
- add_edge/remove_edge: SEMPRE inclua "edge" com source_name, target_name e label
- label só pode ser: subClassOf, domain, range
- Use os nomes dos nós exatamente como aparecem acima
- Prefira poucas mudanças boas a muitas mudanças fracas
- NUNCA invente nomes de nós"""
        }
    ]

    try:
        start = time.time()
        resp = http_requests.post(
            f"{_OLLAMA_HOST}/api/chat",
            json={"model": "granite3.3:8b", "messages": messages, "stream": False, "format": schema, "options": {"temperature": 0.5}},
            timeout=450
        )
        resp.raise_for_status()
        elapsed = time.time() - start
        print(f"[suggest] modelo respondeu em {elapsed:.1f}s")

        parsed = json.loads(resp.json()["message"]["content"].strip())

        op_map = {"add_node": "createNode", "remove_node": "removeNode", "add_edge": "createEdge", "remove_edge": "removeEdge"}
        suggestions = []
        warnings = list(parsed.get("warnings", []))
        existing_names = {n["name"] for n in nodes}

        for op in parsed.get("operations", []):
            action = op_map.get(op.get("op"))
            if not action:
                warnings.append(f"op desconhecida ignorada: {op.get('op')}")
                continue
            reason = op.get("reason", "")

            if op["op"] == "add_node":
                node = op.get("node")
                if not node or not node.get("name"):
                    warnings.append(f"add_node sem campo 'node' ignorado: {reason}")
                    continue
                if node["name"] in existing_names:
                    warnings.append(f"add_node ignorado, nó já existe: {node['name']}")
                else:
                    suggestions.append({"action": action, "id": str(uuid.uuid4()), "name": node["name"], "type": node.get("type", "Class"), "reason": reason})
                    existing_names.add(node["name"])
                edge = op.get("edge")
                if edge and all(k in edge for k in ("source_name", "target_name", "label")):
                    suggestions.append({"action": "createEdge", "id": str(uuid.uuid4()), "source": edge["source_name"], "target": edge["target_name"], "label": edge["label"], "reason": f"(aresta de add_node) {reason}"})

            elif op["op"] == "remove_node":
                node = op.get("node")
                if not node or not node.get("name"):
                    warnings.append(f"remove_node sem campo 'node' ignorado: {reason}")
                    continue
                suggestions.append({"action": action, "name": node["name"], "reason": reason})

            elif op["op"] == "add_edge":
                edge = op.get("edge")
                if not edge or not all(k in edge for k in ("source_name", "target_name", "label")):
                    warnings.append(f"add_edge incompleto ignorado: {reason}")
                    continue
                if edge["source_name"] not in existing_names:
                    warnings.append(f"add_edge ignorado, origem não existe: {edge['source_name']}")
                    continue
                if edge["target_name"] not in existing_names:
                    warnings.append(f"add_edge ignorado, destino não existe: {edge['target_name']}")
                    continue
                suggestions.append({"action": action, "id": str(uuid.uuid4()), "source": edge["source_name"], "target": edge["target_name"], "label": edge["label"], "reason": reason})

            elif op["op"] == "remove_edge":
                edge = op.get("edge")
                if not edge or not all(k in edge for k in ("source_name", "target_name", "label")):
                    warnings.append(f"remove_edge incompleto ignorado: {reason}")
                    continue
                existing_edges = {(id_to_name.get(e["source"], e["source"]), id_to_name.get(e["target"], e["target"]), e["label"]) for e in edges}
                if (edge["source_name"], edge["target_name"], edge["label"]) not in existing_edges:
                    warnings.append(f"remove_edge ignorado, aresta não existe: {edge['source_name']} → {edge['target_name']}")
                    continue
                suggestions.append({"action": action, "source": edge["source_name"], "target": edge["target_name"], "label": edge["label"], "reason": reason})

        return jsonify({"ok": True, "actions": _process_suggestion(suggestions), "warnings": warnings})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


# ── /api/generate ─────────────────────────────────────────────────────────

@views.route('/api/generate', methods=['POST'])
@login_required
def api_generate():
    body = request.get_json()
    if not body:
        return jsonify({"ok": False, "error": "JSON ausente"}), 400

    prompt = body.get("prompt", "").strip()
    if not prompt:
        return jsonify({"ok": False, "error": "prompt vazio"}), 400

    existing_nodes = body.get("existing_nodes", [])
    existing_names_list = [n["name"] for n in existing_nodes]

    EXTRACT_SCHEMA = {
        "type": "object",
        "properties": {
            "nodes_to_create": {"type": "array", "items": {"type": "string"}},
            "connections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "label": {"type": ["string", "null"]}
                    },
                    "required": ["source", "target", "label"]
                }
            }
        },
        "required": ["nodes_to_create", "connections"]
    }

    messages = [
        {"role": "system", "content": "Extraia informações de comandos sobre grafos. Responda APENAS com JSON válido, sem markdown."},
        {
            "role": "user",
            "content": f"""Analise este comando e extraia as informações:

"{prompt}"

Nós que já existem no grafo (não inclua estes em nodes_to_create):
{json.dumps(existing_names_list, ensure_ascii=False)}

Responda com JSON:
{{
  "nodes_to_create": ["lista de classes NOVAS a criar"],
  "connections": [
    {{"source": "classe origem", "target": "classe destino", "label": "nome da relação SE especificado, senão null"}}
  ]
}}

REGRAS:
- nodes_to_create: apenas classes que NÃO estão na lista de existentes
- label: extraia o nome EXATO se o usuário especificar ("com label X", "usando X", "via X")
- label: null se não especificado

EXEMPLOS:
Comando: "gere Cocaina e conecte a SubstanciaPsicoativa usando o label eUma" (SubstanciaPsicoativa já existe)
{{"nodes_to_create": ["Cocaina"], "connections": [{{"source": "Cocaina", "target": "SubstanciaPsicoativa", "label": "eUma"}}]}}

Comando: "Cachorro é tipo de Animal"
{{"nodes_to_create": ["Cachorro", "Animal"], "connections": [{{"source": "Cachorro", "target": "Animal", "label": null}}]}}

Agora extraia do comando dado. Responda APENAS com JSON."""
        }
    ]

    try:
        start = time.time()
        resp = http_requests.post(
            f"{_OLLAMA_HOST}/api/chat",
            json={"model": "granite3.3:8b", "messages": messages, "stream": False, "format": EXTRACT_SCHEMA, "options": {"temperature": 0.3}},
            timeout=450
        )
        resp.raise_for_status()
        elapsed = time.time() - start
        print(f"[generate] modelo respondeu em {elapsed:.1f}s")

        extracted = json.loads(resp.json()["message"]["content"].strip())
        print(f"[generate] extração: {json.dumps(extracted, ensure_ascii=False)}")

        existing_name_set = {n["name"].lower() for n in existing_nodes}
        name_to_id = {n["name"].lower(): n["name"] for n in existing_nodes}
        nodes = []
        warnings = []

        for node_name in extracted.get("nodes_to_create", []):
            node_name = _to_pascal(node_name)
            key = node_name.lower()
            if key in existing_name_set:
                original = next((ex["name"] for ex in existing_nodes if ex["name"].lower() == key), node_name)
                name_to_id[key] = original
                continue
            nid = str(uuid.uuid4())
            name_to_id[key] = nid
            nodes.append({"id": nid, "name": node_name, "type": "Class"})

        edges = []
        for conn in extracted.get("connections", []):
            source = _to_pascal(conn.get("source", ""))
            target = _to_pascal(conn.get("target", ""))
            label  = conn.get("label") or "subClassOf"
            src_id = name_to_id.get(source.lower())
            tgt_id = name_to_id.get(target.lower())
            if not src_id:
                warnings.append(f"aresta ignorada: nó origem '{source}' não existe")
                continue
            if not tgt_id:
                warnings.append(f"aresta ignorada: nó destino '{target}' não existe")
                continue
            edges.append({"source": src_id, "target": tgt_id, "label": label})

        return jsonify({"ok": True, "data": {"nodes": nodes, "edges": edges}, "warnings": warnings})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500
