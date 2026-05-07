import os

from SPARQLWrapper import SPARQLWrapper
from sparqlslurper import SlurpyGraph, GraphDBSlurpyGraph

with open(os.path.join(os.path.dirname(__file__), 'git_describe.txt')) as desc_f:
    description = desc_f.read().strip()

# https://meta.wikimedia.org/wiki/User-Agent_policy:
#   The generic format is <client name>/<version> (<contact information>) <library/framework name>/<version>
#   [<library name>/<version> ...]. Parts that are not applicable can be omitted.

UserAgent = f"PyShEx/{description[1:description.find('-')]} " \
            f"(https://github.com/hsolbrig/PyShEx; solbrig@jhu.edu)"


def SlurpyGraphWithAgent(endpoint: str, *args, persistent_bnodes: bool = False, agent: str | None = None,
                 gdb_slurper: bool | None = False, **kwargs) -> SlurpyGraph:
    rval = GraphDBSlurpyGraph(endpoint, *args, persistent_bnodes=persistent_bnodes, **kwargs) if gdb_slurper else \
        SlurpyGraph(endpoint, *args, persistent_bnodes=persistent_bnodes, **kwargs)
    rval.sparql.agent = agent if agent else UserAgent
    return rval

class SPARQLWrapperWithAgent(SPARQLWrapper):
    def __init__(self, endpoint, updateEndpoint=None, returnFormat=None, defaultGraph=None, agent=UserAgent):
        super().__init__(endpoint, updateEndpoint=updateEndpoint, returnFormat=returnFormat, defaultGraph=defaultGraph,
                         agent=agent)

