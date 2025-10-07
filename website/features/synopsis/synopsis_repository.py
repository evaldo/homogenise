from website.settings import db

class SynopsisRepository:
    def get_individuals_related_by_object_property(self, project_id):
        sparql = f"""                                        
            SELECT distinct (REPLACE(STR(?s), "^.*/([^/]*)$", "$1") as ?subject) (REPLACE(STR(?p), "^.*/([^/]*)$", "$1") as ?predicate) (REPLACE(STR(?o), "^.*/([^/]*)$", "$1") as ?object)
            WHERE {{
                ?s ?p ?o .                      
                FILTER(?p NOT IN (<http://semanticscience.org/resource/hasUnit>, rdfs:domain, rdfs:range, rdfs:subPropertyOf, rdf:first, rdf:rest, owl:members, <http://www.w3.org/ns/prov#generatedAtTime>, owl:allValuesFrom, <http://semanticscience.org/resource/isAttributeOf>)) .
                FILTER(?o NOT IN (owl:ObjectProperty, owl:Class, owl:NamedIndividual, owl:AllDisjointClasses, owl:Restriction, <http://semanticscience.org/resource/isAttributeOf>)) .    
                FILTER (!isBlank(?o)) . 
                FILTER (!isBlank(?s)) .
                FILTER(?o != '') .
                ?p rdfs:subPropertyOf owl:topObjectProperty        
            }}
        """
        
        with db.get_allegro(project_id) as conn:
            with conn.executeTupleQuery(sparql) as results:
                return self.__format_results(results)
            
    def get_classes_related_by_superclasses(self, project_id):
        sparql = f"""                                        
            SELECT distinct (REPLACE(STR(?s), "^.*/([^/]*)$", "$1") as ?subject) (REPLACE(STR(?p), "^.*/([^/]*)$", "$1") as ?predicate) (REPLACE(STR(?o), "^.*/([^/]*)$", "$1") as ?object)
            WHERE {{
                ?s ?p ?o .                      
                FILTER(?p NOT IN (<http://semanticscience.org/resource/hasUnit>, rdfs:domain, rdfs:range, rdfs:subPropertyOf, rdf:first, rdf:rest, owl:members, <http://www.w3.org/ns/prov#generatedAtTime>, owl:allValuesFrom, <http://semanticscience.org/resource/isAttributeOf>)) .
                FILTER(?o NOT IN (owl:ObjectProperty, owl:Class, owl:NamedIndividual, owl:AllDisjointClasses, owl:Restriction, <http://semanticscience.org/resource/isAttributeOf>)) .    
                FILTER (!isBlank(?o)) . 
                FILTER (!isBlank(?s)) .
                FILTER(?o != '') .
                ?s rdfs:subClassOf ?o     
            }}
        """
        
        with db.get_allegro(project_id) as conn:
            with conn.executeTupleQuery(sparql) as results:
                return self.__format_results(results)
            
    def get_classes_related_by_object_property_domains_and_ranges(self, project_id):
        sparql = f"""                                        
            SELECT distinct (REPLACE(STR(?s), "^.*/([^/]*)$", "$1") as ?subject) (REPLACE(STR(?p), "^.*/([^/]*)$", "$1") as ?predicate) (REPLACE(STR(?o), "^.*/([^/]*)$", "$1") as ?object)
            WHERE {{                    
                FILTER(?p NOT IN (<http://semanticscience.org/resource/hasUnit>, rdfs:domain, rdfs:range, rdfs:subPropertyOf, rdf:first, rdf:rest, owl:members, <http://www.w3.org/ns/prov#generatedAtTime>, owl:allValuesFrom, <http://semanticscience.org/resource/isAttributeOf>)) .
                FILTER(?o NOT IN (owl:ObjectProperty, owl:Class, owl:NamedIndividual, owl:AllDisjointClasses, owl:Restriction, <http://semanticscience.org/resource/isAttributeOf>)) .    
                FILTER (!isBlank(?o)) . 
                FILTER (!isBlank(?s)) .
                FILTER(?o != '') .
                ?p a owl:ObjectProperty .
                ?p rdfs:domain ?s .
                ?s a owl:Class .
                ?o a owl:Class .
                ?p rdfs:range ?o 
            }}
        """
        
        with db.get_allegro(project_id) as conn:
            with conn.executeTupleQuery(sparql) as results:
                return self.__format_results(results)
            
    def __format_results(self, results):
        return list(
            map(
                lambda result: (self.__remove_prefix(result.getValue('subject')), self.__remove_prefix(result.getValue('predicate')), self.__remove_prefix(result.getValue('object'))),
                results
            )
        )
    
    def __remove_prefix(self, property):
        prefix, word = str(property).replace('"', "").split("#")

        return word if word else prefix