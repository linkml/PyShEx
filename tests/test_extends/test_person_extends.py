"""EXTENDS validation: person-extends fixture (labeled, OR, AND+NOT parents, diamond
inheritance through <Item>).  See the companion implementations in Apache Jena
(jena-shex/docs/matching-search-optimization.md), rudof (docs/dev/feasibility-model.md)
and shex.js, from which the allocation model (triples -> triple constraints, shared
ancestors allocating to every extension) and the feasibility guard are ported."""
import unittest
from pathlib import Path

from pyshex import ShExEvaluator

DATA = Path(__file__).parent.parent / 'data'
SCHEMA = (DATA / 'person-extends.json').read_text()
FOCUS = 'http://instance.example/#alice'
START = 'http://schema.example/Person'

ALICE = """BASE <http://instance.example/>
PREFIX ex: <http://a.example/ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX schema: <http://schema.org/>
<#alice> ex:id <TheAlice> ; ex:rolls ex:Engineer , ex:Human ;
  foaf:name "alice" ; foaf:mbox <mailto:alice@co.example> ;
  ex:SlideRoolLength 11 ; ex:PocketProtectorMaterial "plastic" ;
  ex:badgeNumber 58008 .
"""


def evaluates(rdf: str) -> bool:
    return ShExEvaluator(rdf=rdf, schema=SCHEMA, focus=FOCUS, start=START).evaluate()[0].result


class PersonExtendsTestCase(unittest.TestCase):
    def test_conformant(self) -> None:
        self.assertTrue(evaluates(ALICE))

    def test_schema_org_flavour_selects_other_branch(self) -> None:
        self.assertTrue(evaluates(ALICE.replace('foaf:', 'schema:')))

    def test_boss_flavour_selects_other_tool(self) -> None:
        self.assertTrue(evaluates(ALICE
            .replace('ex:rolls ex:Engineer', 'ex:rolls ex:Manager')
            .replace('ex:SlideRoolLength 11', 'ex:sunglassesBrand "RayBan"')
            .replace('ex:PocketProtectorMaterial "plastic"', 'ex:tieMaterial "silk"')))

    def test_robot_fails_negated_conjunct(self) -> None:
        # The Robot role reaches <Contact> through the shared <Item> ancestor
        # (diamond): the allocation cannot hide it from NOT EXTRA ex:rolls {...[ex:Robot]}
        self.assertFalse(evaluates(ALICE.replace('ex:Engineer , ex:Human', 'ex:Engineer , ex:Human , ex:Robot')))

    def test_missing_human_fails_extra_conjunct(self) -> None:
        self.assertFalse(evaluates(ALICE.replace(' , ex:Human', '')))

    def test_stray_predicate_fails_closed(self) -> None:
        self.assertFalse(evaluates(ALICE.replace('ex:badgeNumber 58008', 'ex:glovesSize "XL" ; ex:badgeNumber 58008')))

    def test_missing_badge_fails_local_expression(self) -> None:
        self.assertFalse(evaluates(ALICE.replace(' ;\n  ex:badgeNumber 58008', '')))


if __name__ == '__main__':
    unittest.main()
