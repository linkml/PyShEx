from pyshex import PrefixLibrary, ShExEvaluator

schema = """
PREFIX ex: <http://ex.example/#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX school: <http://school.example/#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>

school:enrolleeAge xsd:integer MinInclusive 13 MaxInclusive 20 

school:Enrollee {
  foaf:age @school:enrolleeAge ;
  ex:hasGuardian IRI {1,2}
}

school:Encapsulated {
    ex:hasMany {
        (ex:hasGuardian IRI {1,2}; 
         ex:hasGuardian IRI {1,2}){3}
    }{2}
} 
"""

rdf = """
PREFIX ex: <http://ex.example/#>
PREFIX inst: <http://example.com/users/>
PREFIX school: <http://school.example/#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>

inst:Eric foaf:age 20 ;
  ex:hasGuardian inst:PersonA, inst:PersonB, inst:PersonC .

inst:Fred ex:hasMany [ex:hasGuardian inst:Animal1, inst:Animal2], [ex:hasGuardian inst:Animal3].
"""


def test_eric():
    p = PrefixLibrary(rdf)
    for result in ShExEvaluator(rdf=rdf, schema=schema,
                                focus=p.INST.Eric,
                                start=p.SCHOOL.Enrollee).evaluate(debug=False):
        print(f"{result.focus}: {'Passing' if result.result else 'Failing'}: \n{result.reason}")
        assert not result.result


def test_fred():
    p = PrefixLibrary(rdf)
    for result in ShExEvaluator(rdf=rdf, schema=schema,
                                focus=p.INST.Fred,
                                start=p.SCHOOL.Encapsulated).evaluate(debug=False):
        print(f"{result.focus}: {'Passing' if result.result else 'Failing'}: \n{result.reason}")
        assert not result.result