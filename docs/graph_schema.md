# Wikipedia Dispute Graph Schema

## Overview

This document describes the graph data model used to represent Wikipedia
dispute resolution data and the planned extension to Wikidata for semantic
enrichment.

The graph is implemented as a NetworkX `MultiDiGraph` with typed nodes and
edges. This allows multiple parallel edges between the same pair of nodes
(e.g., an editor can both REVERT another editor and CO-OCCUR with them).

---

## Current Schema

### Node Types

| Type | ID Pattern | Required Attributes | Optional Attributes |
|------|-----------|---------------------|---------------------|
| **editor** | `editor:{username}` | `node_type`, `label` | `total_edits`, `total_reverts`, `revert_ratio`, `case_count`, `cases` |
| **article** | `article:{title}` | `node_type`, `label` | `url`, `topic_area` |
| **arbcase** | `case:{case_name}` | `node_type`, `label`, `case_prefix` | `duration_days`, `total_editors`, `total_revisions`, `earliest`, `latest` |

### Edge Types

| Type | Direction | Source → Target | Attributes |
|------|-----------|----------------|------------|
| **REVERTS** | Directed | editor → editor | `count`, `pages[]`, `case` |
| **EDITS_CASE** | Directed | editor → arbcase | `edit_count`, `revert_count`, `subpages[]`, `active_days` |
| **EDITS_ARTICLE** | Directed | editor → article | `edit_count`, `case` |
| **SUBJECT_OF** | Directed | article → arbcase | *(none)* |
| **CO_OCCURS** | Directed* | editor → editor | `shared_cases[]`, `shared_count` |

> *CO_OCCURS is semantically undirected but stored as a directed edge for
> consistency with the MultiDiGraph container. Use
> `editor_cooccurrence_subgraph()` to get an undirected projection.

---

## Wikidata Extension Schema (Planned)

### Rationale

Wikipedia articles map to Wikidata items via Q-identifiers. Enriching
article nodes with Wikidata metadata enables:

1. **Topic classification** — group disputes by Wikidata categories
   (e.g., `Q7163` "politics", `Q21198` "computer science")
2. **Semantic relatedness** — articles related through Wikidata properties
   form implicit dispute propagation pathways
3. **Comparison to knowledge graph literature** — schema aligns with RDF
   triple patterns used by Wikidata, DBpedia, and YAGO

### New Node Attributes (on `article` nodes)

| Attribute | Type | Wikidata Source | Description |
|-----------|------|----------------|-------------|
| `wikidata_qid` | `str` | Item ID | e.g., `Q7163` |
| `wikidata_label` | `str` | `rdfs:label` | Canonical label |
| `wikidata_description` | `str` | `schema:description` | Short description |
| `wikidata_instance_of` | `list[str]` | `P31` (instance of) | e.g., `["Q5107 continent"]` |
| `wikidata_subclass_of` | `list[str]` | `P279` (subclass of) | Broader category chain |
| `wikidata_main_subject` | `list[str]` | `P921` (main subject) | Topics this article is about |
| `wikidata_categories` | `list[str]` | Derived | Human-readable topic tags |

### New Edge Type

| Type | Direction | Source → Target | Attributes | Wikidata Source |
|------|-----------|----------------|------------|-----------------|
| **RELATED_TO** | Undirected | article ↔ article | `relation`, `property_id` | `P921`, `P279`, `P361` (part of) |

### Wikidata Property Mappings

| Wikidata Property | ID | Graph Usage |
|-------------------|----|-------------|
| instance of | `P31` | Classify article type (person, event, concept, place) |
| subclass of | `P279` | Build topic hierarchy |
| main subject | `P921` | Link articles to abstract topics |
| part of | `P361` | Geographic/organizational containment |
| different from | `P1889` | Potentially contested identities |
| topic's main category | `P910` | Map to Wikipedia categories |

### SPARQL Query Templates

#### Fetch Q-ID for a Wikipedia article title

```sparql
SELECT ?item WHERE {
  ?article schema:about ?item ;
           schema:isPartOf <https://en.wikipedia.org/> ;
           schema:name "{article_title}"@en .
}
```

#### Fetch topic categories for a Q-ID

```sparql
SELECT ?item ?itemLabel ?instanceOf ?instanceOfLabel ?subjectOf ?subjectOfLabel WHERE {
  BIND(wd:{qid} AS ?item)
  OPTIONAL { ?item wdt:P31 ?instanceOf . }
  OPTIONAL { ?item wdt:P921 ?subjectOf . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
```

#### Find related items (shared main subject)

```sparql
SELECT ?item1 ?item1Label ?item2 ?item2Label ?topic ?topicLabel WHERE {
  ?item1 wdt:P921 ?topic .
  ?item2 wdt:P921 ?topic .
  FILTER(?item1 != ?item2)
  VALUES ?item1 { wd:{qid} }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
LIMIT 50
```

---

## RDF / Semantic Web Mapping

The graph schema maps cleanly to RDF triples for interoperability with
semantic web tools:

```turtle
# Prefixes
@prefix wd:   <http://www.wikidata.org/entity/> .
@prefix wdt:  <http://www.wikidata.org/prop/direct/> .
@prefix wdis: <https://wikipedia-disputes.example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

# Editor node
wdis:editor/Alice
    a wdis:Editor ;
    rdfs:label "Alice" ;
    wdis:totalEdits 42 ;
    wdis:revertRatio 0.15 .

# Article node (with Wikidata enrichment)
wdis:article/Climate_change
    a wdis:Article ;
    rdfs:label "Climate change" ;
    owl:sameAs wd:Q7942 ;
    wdt:P31 wd:Q7163 ;           # instance of: politics
    wdt:P921 wd:Q11451 .         # main subject: climate change

# Edges
wdis:editor/Alice wdis:reverts wdis:editor/Bob .
wdis:editor/Alice wdis:editsCase wdis:case/Climate_change .
wdis:article/Climate_change wdis:subjectOf wdis:case/Climate_change .
```

---

## Comparison to Existing Knowledge Graphs

| Feature | This Project | Wikidata | DBpedia | YAGO |
|---------|-------------|----------|---------|------|
| **Focus** | Dispute/conflict relationships | General knowledge | Structured Wikipedia infoboxes | Taxonomic + temporal |
| **Node types** | Editor, Article, Case | Item, Property | Resource | Entity, Event, Fact |
| **Edge semantics** | Social (revert, co-occur) + structural (subject_of) | General (P-properties) | Ontological (type, relation) | Temporal + spatial |
| **Temporal** | Timestamps on edges, case duration | Statement qualifiers | Limited | First-class time dimension |
| **Unique value** | Editor behavior & conflict dynamics | Breadth of coverage | Structured data extraction | Temporal reasoning |

### Integration Points

1. **Wikidata → Article enrichment**: Q-IDs, categories, topic hierarchy
2. **DBpedia → Infobox data**: structured attributes for disputed articles
3. **WikiWho → Edit attribution**: precise authorship tracking at token level
4. **ORES → Quality scores**: predicted article quality and editor reliability

---

## Implementation Roadmap

### Phase 1 (Current): In-Memory Graph with NetworkX
- Build graph from existing arbitration case data
- Compute centrality, community detection, cross-case metrics
- Explore in Marimo reactive notebook

### Phase 2: Wikidata Enrichment
- Query Wikidata SPARQL endpoint for article Q-IDs
- Fetch P31/P279/P921 triples per article
- Add RELATED_TO edges between articles sharing topics
- Topic-based dispute clustering analysis

### Phase 3: Persistent Graph Store (if scale demands)
- Evaluate Neo4j vs. graph-tool vs. staying with NetworkX
- Decision criteria: >100K nodes, need for concurrent queries, dashboard integration
- Export Cypher/GEXF for visualization tools (Gephi, yEd)

### Phase 4: Dashboard Integration
- Interactive graph visualization in React dashboard
- Force-directed layout with filtering by case, editor, topic
- Drill-down from graph node to case detail view
