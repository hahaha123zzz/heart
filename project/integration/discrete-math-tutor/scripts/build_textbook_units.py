"""Build the complete textbook-unit retrieval index."""

import json

from knowledge.knowledge_units import build_unit_index


if __name__ == "__main__":
    print(json.dumps(build_unit_index(embed=True), ensure_ascii=False))
