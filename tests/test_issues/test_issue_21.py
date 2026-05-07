import pytest
from pyshex import ShExEvaluator


SHEX = """
BASE <http://example.org/ex/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX ex: <http://ex.example/#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX : <http://hl7.org/fhir/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
start = @<BloodPressureMeasurementShape>
<PatientShape> {
:name xsd:string*;
:birthdate xsd:date?;
}
<BloodPressureMeasurementShape> {
  rdfs:label  xsd:string ;
  :subject @<PatientShape> ;
  :hasmeasurementDate  @<BPDateShape> ;
  :valueSBP @<SBPvalueShape> ;
  :valueDBP @<DBPvalueShape> ;
  :valueABP @<ABPvalueShape>? ;
  (:hasMethod  @<BPMeasurementInvasiveMethodShape> |
   :hasMethod @<BPMeasurementNoninvasiveMethodShape> ) ;
  :hasLocation @<BPMeasurementLocationShape>? ;
  :hasType @<DEPShape>? ;
  :isAffectedBy @<BodyPositionShape>?
}
<SBPvalueShape> {
   :valueS  xsd:integer;
}
<DBPvalueShape> {
   :valueD  xsd:integer;
}
<ABPvalueShape> {
   :valueA  xsd:integer;
}
<BPMeasurementMethodShape> {
   :method [<invasive> <non-invasive>];
}
<BPMeasurementInvasiveMethodShape> {
   :method [<invasive>];
}
<BPMeasurementNoninvasiveMethodShape> {
   :method [<non-invasive>];
}
<BPDateShape> {
   :date  xsd:date;
}
<BPMeasurementLocationShape> {
   :location [<arm> <leg> <ankle>];
}
<DEPShape> {
   :type [<typeIV> <typeV>];
}
<BodyPositionShape> {
   :position [<sittingposition> <recumbentbodyposition> <orthostaticbodyposition> <positionwithtilt> <trendelenburgposition>];
}
"""

RDF = """
BASE <http://example.org/ex/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX ex: <http://ex.example/#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX : <http://hl7.org/fhir/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
<Patient2>
  :name "Bob" ;
  :birthdate "1999-12-31"^^xsd:date ;
  :has :BloodPressureMeasurementShape .
<BPDate1>
  :date "2010-12-31"^^xsd:date.
<SBP1>
  :valueS 140 .
<DBP1>
  :valueD 90 .
<ABP1>
  :valueA 97 .
<BPMMethod1>
  :method <non-invasive> .
<BPMLocation1>
  :location <arm> .
<BodyPosition1>
  :position <sittingposition> .
<DEP1>
  :type <typeIV>.
<BPM1>
  a :BloodPressureMeasurementShape ;
  rdfs:label "First BP measurement" ;
  :subject  <Patient2> ;
  :hasmeasurementDate <BPDate1> ;
  :valueSBP <SBP1> ;
  :valueDBP <DBP1> ;
  :valueABP <ABP1> ;
  :method <BPMMethod1> ;
  :location <BPMLocation1> ;
  :type <DEP1> ;
  :position <BodyPosition1> .
"""

FOCUS = "http://example.org/ex/BPM1"


def test_bpm1_evaluates_as_failing() -> None:
    """BPM1 should fail ShEx validation (regression: previously caused a hang)."""
    results = ShExEvaluator().evaluate(RDF, SHEX, focus=FOCUS, debug=False)

    for r in results:
        if r.result:
            print("PASS")
        else:
            print(f"FAIL: {r.reason}")

    assert [r.result for r in results] == [False]