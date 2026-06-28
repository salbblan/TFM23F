// ── Importación del grafo 23-F en Neo4j ──────────────────────────
// Copia neo4j_nodos.csv y neo4j_aristas.csv a la carpeta 'import' de
// tu base de datos Neo4j antes de ejecutar este script.

// ── 1. Restricción de unicidad (también crea índice automáticamente) ──
CREATE CONSTRAINT entidad_id_unica IF NOT EXISTS
FOR (e:Entidad) REQUIRE e.id IS UNIQUE;

// ── 2. Cargar nodos (una pasada por tipo, añade la etiqueta específica) ──
// -- Nodos de tipo Persona --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodos.csv' AS row
WITH row WHERE row.tipo = 'Persona'
MERGE (n:Entidad {id: row.id})
SET n.label = row.label, n.tipo = row.tipo
SET n:`Persona`;

// -- Nodos de tipo Institución --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodos.csv' AS row
WITH row WHERE row.tipo = 'Institución'
MERGE (n:Entidad {id: row.id})
SET n.label = row.label, n.tipo = row.tipo
SET n:`Institución`;

// -- Nodos de tipo Lugar --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodos.csv' AS row
WITH row WHERE row.tipo = 'Lugar'
MERGE (n:Entidad {id: row.id})
SET n.label = row.label, n.tipo = row.tipo
SET n:`Lugar`;

// -- Nodos de tipo Documento --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodos.csv' AS row
WITH row WHERE row.tipo = 'Documento'
MERGE (n:Entidad {id: row.id})
SET n.label = row.label, n.tipo = row.tipo
SET n.documento_id = row.documento_id, n.url = row.url, n.fecha = row.fecha
SET n:`Documento`;

// ── 3. Cargar aristas (una pasada por tipo de relación) ──
// -- Aristas de tipo CONOCE --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'CONOCE'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:CONOCE]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo INFORMA --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'INFORMA'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:INFORMA]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo PERTENECE --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'PERTENECE'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:PERTENECE]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo LLAMA --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'LLAMA'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:LLAMA]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo ASISTE --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'ASISTE'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:ASISTE]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo ORDENA --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'ORDENA'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:ORDENA]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo MENCIONA --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'MENCIONA'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:MENCIONA]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo PROPONE --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'PROPONE'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:PROPONE]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo SOLICITA --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'SOLICITA'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:SOLICITA]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo COLABORA --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'COLABORA'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:COLABORA]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo AUTORIZA --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'AUTORIZA'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:AUTORIZA]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);

// -- Aristas de tipo NIEGA --
LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row
WITH row WHERE row.tipo = 'NIEGA'
MATCH (a:Entidad {id: row.origen})
MATCH (b:Entidad {id: row.destino})
MERGE (a)-[r:NIEGA]->(b)
SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,
    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,
    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,
    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,
    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,
    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);
