from semantic_weaver import (
    ColumnMetadata,
    DatabaseMetadata,
    SemanticGuardrail,
    SemanticMetadataIndex,
    generate_sql_from_metadata,
)


def test_population_metadata_detects_equivocation():
    registry = SemanticMetadataIndex()
    registry.register(
        DatabaseMetadata(
            table_name="stat_census_population",
            description="国勢調査の人口。実際に居住している人間の数。",
            source_system="stat_census",
            columns=[
                ColumnMetadata(
                    column_name="population",
                    definition="実態人口",
                    scope="常住人口",
                    measurement_basis="実際に居住している人間の数",
                    unit="人",
                )
            ],
        )
    )
    registry.register(
        DatabaseMetadata(
            table_name="residence_registry_population",
            description="住民基本台帳の人口。住民票に登録されている人数。",
            source_system="residence_registry",
            columns=[
                ColumnMetadata(
                    column_name="registered_population",
                    definition="登録人口",
                    scope="住民票に登録されている人数",
                    measurement_basis="住民票に記載されている人数",
                    unit="人",
                )
            ],
        )
    )

    hits = registry.search("A市の人口推移")
    assert len(hits) >= 2

    guardrail = SemanticGuardrail()
    clarification = guardrail.check_equivocation(hits)
    assert clarification is not None
    assert "実態" in clarification or "登録" in clarification


def test_working_people_synonyms_resolve_to_correct_columns():
    registry = SemanticMetadataIndex()
    registry.register(
        DatabaseMetadata(
            table_name="economic_census_workers",
            description="経済センサスの働く人。従業者を表す。",
            source_system="economic_census",
            columns=[
                ColumnMetadata(
                    column_name="workers",
                    definition="従業者",
                    scope="経済センサスの従業者",
                    measurement_basis="雇用に従事している人",
                    unit="人",
                    aliases=["働く人", "従業者"],
                )
            ],
        )
    )
    registry.register(
        DatabaseMetadata(
            table_name="corporate_statistics_workers",
            description="法人企業統計の働く人。役員及び従業員を表す。",
            source_system="corporate_statistics",
            columns=[
                ColumnMetadata(
                    column_name="employees",
                    definition="役員及び従業員",
                    scope="法人企業統計の従事者",
                    measurement_basis="企業に所属する労働者と役員",
                    unit="人",
                    aliases=["働く人", "役員及び従業員"],
                )
            ],
        )
    )

    hits = registry.search("東京都の働く人の数")
    assert len(hits) >= 2

    selected = registry.select_columns_for_query("東京都の働く人の数")
    assert {item.column_name for item in selected} == {"workers", "employees"}


def test_sql_generation_uses_metadata_and_blocks_unsafe_merge():
    index = SemanticMetadataIndex()
    index.register(
        DatabaseMetadata(
            table_name="stat_census_population",
            description="国勢調査の人口。実際に居住している人間の数。",
            source_system="stat_census",
            columns=[
                ColumnMetadata(
                    column_name="population",
                    definition="実態人口",
                    scope="常住人口",
                    measurement_basis="実際に居住している人間の数",
                    unit="人",
                )
            ],
        )
    )
    index.register(
        DatabaseMetadata(
            table_name="residence_registry_population",
            description="住民基本台帳の人口。住民票に登録されている人数。",
            source_system="residence_registry",
            columns=[
                ColumnMetadata(
                    column_name="registered_population",
                    definition="登録人口",
                    scope="住民票に登録されている人数",
                    measurement_basis="住民票に記載されている人数",
                    unit="人",
                )
            ],
        )
    )

    query = "A市の人口推移"
    candidates = index.search(query)
    sql = generate_sql_from_metadata(candidates, query)
    assert "stat_census_population" in sql or "residence_registry_population" in sql
    assert "SELECT" in sql.upper()

    guardrail = SemanticGuardrail()
    assert guardrail.check_equivocation(candidates) is not None
