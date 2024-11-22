from pyshex.shex_evaluator import ShExEvaluator
from pyshex.user_agent import SlurpyGraphWithAgent
from pyshex.utils.sparql_query import SPARQLQuery

# SPARQL Endpoint
endpoint = 'http://wifo5-04.informatik.uni-mannheim.de/drugbank/sparql'

# SPARQL Query
sparql = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX vocabClass: <http://wifo5-04.informatik.uni-mannheim.de/drugbank/vocab/resource/class/>

SELECT DISTINCT ?item WHERE {
  ?item rdf:type vocabClass:Offer
}
LIMIT 10
"""

# ShEx Expression
shex = """
PREFIX drugbank: <http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugbank/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX : <http://example.org/t1/>

START=@:S1

:S1 {foaf:page IRI+ ;                     # one or more foaf pages
     drugbank:limsDrugId xsd:string       # and exactly one drug id
}"""


# Do the evaluation
result = ShExEvaluator(SlurpyGraphWithAgent(endpoint),                                   # RDF source
                       shex,                                                    # ShEx definition
                       SPARQLQuery(endpoint, sparql).focus_nodes()).evaluate()  # Source off focus nodes

# Print the results
for r in result:
    print(f"{r.focus}: ", end="")
    if not r.result:
        print(f"FAIL: {r.reason}")
    else:
        print("PASS")
