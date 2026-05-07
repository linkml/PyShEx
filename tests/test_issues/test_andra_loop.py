# import jsonasobj
# import requests
# from SPARQLWrapper import JSON
# from ShExJSG import ShExC
#
# from pyshex import ShExEvaluator
# from pyshex.user_agent import SlurpyGraphWithAgent, SPARQLWrapperWithAgent
#
#
# def get_sparql_dataframe(service, query):
#     """
#     Helper function to convert SPARQL results into a Pandas data frame.
#     """
#     sparql = SPARQLWrapperWithAgent(service)
#     sparql.setQuery(query)
#     sparql.setReturnFormat(JSON)
#     result = sparql.query()
#
#     processed_results = jsonasobj.load(result.response)
#     cols = processed_results.head.vars
#
#     out = []
#     for row in processed_results.results.bindings:
#         item = []
#         for c in cols:
#             item.append(row._as_dict.get(c, {}).get('value'))
#         out.append(item)
#
#     return pd.DataFrame(out, columns=cols)
#
# def run_shex_manifest():
#     #manifest = \
#     #    "https://raw.githubusercontent.com/SuLab/Genewiki-ShEx/master/pathways/wikipathways/manifest_all.json"
#     # manifest = jsonasobj.loads(requests.get(os.environ['MANIFEST_URL']).text)
#     manifest_loc = "https://raw.githubusercontent.com/SuLab/Genewiki-ShEx/master/diseases/manifest_all.json"
#     manifest = jsonasobj.loads(requests.get(manifest_loc).text)
#     # print(os.environ['MANIFEST_URL'])
#     for case in manifest:
#         print(case._as_json_dumps())
#         if case.data.startswith("Endpoint:"):
#             sparql_endpoint = case.data.replace("Endpoint: ", "")
#             schema = requests.get(case.schemaURL).text
#             shex = ShExC(schema).schema
#             # print("==== Schema =====")
#             #print(shex._as_json_dumps())
#
#             evaluator = ShExEvaluator(schema=shex, debug=False)
#             sparql_query = case.queryMap.replace("SPARQL '''", "").replace("'''@START", "")
#
#             df = get_sparql_dataframe(sparql_endpoint, sparql_query)
#             for wdid in df.item:
#                 slurpeddata = SlurpyGraphWithAgent(sparql_endpoint)
#                 # slurpeddata = requests.get(wdid + ".ttl")
#
#                 results = evaluator.evaluate(rdf=slurpeddata, focus=wdid, debug=False, debug_slurps=True)
#                 for result in results:
#                     if result.result:
#                         print(str(result.focus) + ": CONFORMS")
#                     else:
#                         if str(result.focus) in [
#                             "http://www.wikidata.org/entity/Q33525",
#                             "http://www.wikidata.org/entity/Q62736",
#                             "http://www.wikidata.org/entity/Q112670"
#                         ]:
#                             continue
#                         print(
#                             "item with issue: " + str(result.focus) + " - " + "shape applied: " + str(result.start))
#

# run_shex_manifest()