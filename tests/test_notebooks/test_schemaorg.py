from pyshex import ShExEvaluator


DS_SHEX = """
PREFIX :   <http://example.org/>
PREFIX schema: <http://schema.org/>
PREFIX techdoc: <http://schema.org/>
BASE <http://schema.org/shex>

# Basic utilities
# Note that we aren't attempting general domain/range checks here: 

<#BasicUrlSh> ((IRI OR LITERAL) AND CLOSED {}  AND /^(https?|gopher|ftps?):/)

<#SchemaText> LITERAL OR xsd:string 

# assumes we have loaded the subClassOf type hierarchy:
<#SubDataset> <#SubDatasetKnownClosure> OR { rdfs:subClassOf @<#SubDataset> }

# doesn't assume we have loaded the subClassOf type hierarchy:
<#SubDatasetKnownClosure> [schema:Dataset schema:DataFeed]

<#SubWork> [schema:CreativeWork] OR { rdfs:subClassOf @<#SubWork> }

#####################

# minimal Dataset shape: an identified type with a name and url
<#BasicDatasetShape> EXTRA a
  {   
    a <#SubDataset>;
    schema:name @<#SchemaText> +;
    schema:url @<#BasicUrlSh> +;

    # Anything agreed here by all the more needy shapes below
    # ...
    schema:sameAs @<#BasicUrlSh> *;
    schema:thumbnailUrl @<#BasicUrlSh> *;
  }  
"""

GOOD_EG_1 = """    {
      "@id": "http://example.org/good_",
      "@type":"Dataset",
      "@context": {
          "@language": "en",
          "@vocab": "http://schema.org/"
      },
      "name":"NCDC Storm Events Database",
      "description":"Storm Data is provided by the National Weather Service (NWS) and contain statistics on...",
      "url":"https://catalog.data.gov/dataset/ncdc-storm-events-database",
      "sameAs":"https://gis.ncdc.noaa.gov/geoportal/catalog/search/resource/details.page?id=gov.noaa.ncdc:C00510",
      "identifier": ["https://doi.org/10.1000/182",
                     "https://identifiers.org/ark:/12345/fk1234"],
      "keywords":[
         "ATMOSPHERE > ATMOSPHERIC PHENOMENA > CYCLONES",
         "ATMOSPHERE > ATMOSPHERIC PHENOMENA > DROUGHT",
         "ATMOSPHERE > ATMOSPHERIC PHENOMENA > FOG",
         "ATMOSPHERE > ATMOSPHERIC PHENOMENA > FREEZE"
      ],
      "license" : "https://creativecommons.org/publicdomain/zero/1.0/",
      "hasPart" : [
        {
          "@type": "Dataset",
          "name": "Sub dataset 01",
          "description": "Informative description of the first subdataset...",
          "license" : "https://creativecommons.org/publicdomain/zero/1.0/"
        },
        {
          "@type": "Dataset",
          "name": "Sub dataset 02",
          "description": "Informative description of the second subdataset...",
          "license" : "https://creativecommons.org/publicdomain/zero/1.0/"
        }
      ],
      "creator":{
         "@type":"Organization",
         "url": "https://www.ncei.noaa.gov/",
         "name":"OC/NOAA/NESDIS/NCEI > National Centers for Environmental Information, NESDIS, NOAA, U.S. Department of Commerce",
         "contactPoint":{
            "@type":"ContactPoint",
            "contactType": "customer service",
            "telephone":"+1-828-271-4800",
            "email":"ncei.orders@noaa.gov"
         }
      },
      "includedInDataCatalog":{
         "@type":"DataCatalog",
         "name":"data.gov"
      },
      "distribution":[
         {
            "@type":"DataDownload",
            "encodingFormat":"CSV",
            "contentUrl":"http://www.ncdc.noaa.gov/stormevents/ftp.jsp"
         },
         {
            "@type":"DataDownload",
            "encodingFormat":"XML",
            "contentUrl":"http://gis.ncdc.noaa.gov/all-records/catalog/search/resource/details.page?id=gov.noaa.ncdc:C00510"
         }
      ],
      "temporalCoverage":"1950-01-01/2013-12-18",
      "spatialCoverage":{
         "@type":"Place",
         "geo":{
            "@type":"GeoShape",
            "box":"18.0 -65.0 72.0 172.0"
         }
      }
    }
"""

FOCUS = "http://example.org/good_"
START = "http://schema.org/shex#BasicDatasetShape"


def test_basic_dataset_shape_conforms() -> None:
    results = ShExEvaluator(schema=DS_SHEX, start=START).evaluate(
        GOOD_EG_1, focus=FOCUS, rdf_format="json-ld"
    )
    failures = [(r.focus, r.reason) for r in results if not r.result]
    assert not failures, f"ShEx validation failed:\n" + "\n".join(r for _, r in failures)