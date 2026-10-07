# ---------------------- Guide composition service ---------------------- #
from .service import CollectionDescriber

# ---------------------- Bounded, stamp-validated guide cache ---------------------- #
from .cache import DESCRIBE_CACHE, DescribeCache

# ---------------------- Guide building blocks (pure + bounded reads) ---------------------- #
from .field_guide_builder import FieldGuideBuilder
from .search_guide import SearchGuide
from .example_requests import ExampleRequestBuilder

# ---------------------- API response contract ---------------------- #
from .models import CollectionDescription, FieldGuide, SearchTargetGuide

# ------------------- Public API ------------------- #
__all__ = [
    "CollectionDescriber",
    "DESCRIBE_CACHE",
    "DescribeCache",
    "FieldGuideBuilder",
    "SearchGuide",
    "ExampleRequestBuilder",
    "CollectionDescription",
    "FieldGuide",
    "SearchTargetGuide",
]
