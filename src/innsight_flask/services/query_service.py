"""Query service for parsing and extracting information from user queries."""

from ..parser import parse_query, extract_location_from_query
from ..exceptions import ParseError


class QueryService:
    """Service for parsing and extracting information from user queries."""
    
    def extract_search_term(self, query: str) -> str:
        """Extract and validate search term from query."""
        parsed_query = parse_query(query)
        location = extract_location_from_query(parsed_query, query)
        poi = parsed_query.get('poi', '')
        
        if not location and not poi:
            raise ParseError("無法判斷地名或主行程")
        
        return location if location else poi