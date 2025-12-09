"""
Parser module for extracting days and filters from Chinese text queries.

This module provides functionality to parse Chinese text queries for:
1. Duration extraction (days/nights) with support for both Arabic and Chinese numerals
2. Filter extraction for accommodation features (parking, wheelchair access, kids-friendly, pet-friendly)
3. POI (Point of Interest) extraction for main travel activities and attractions
4. Location extraction from query text and POI keywords
"""

import re
import os
from functools import lru_cache
from typing import List, Optional, Dict, Set

from .utils import combine_tokens
from .exceptions import DaysOutOfRangeError, ParseConflictError, ParseError


class ChineseNumberParser:
    """Helper class for parsing Chinese numbers."""
    
    CHINESE_NUMBERS = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
        '十': 10, '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '十六': 16,
        '十七': 17, '十八': 18, '十九': 19, '二十': 20, '兩': 2, '半': 0.5
    }
    
    @classmethod
    def parse(cls, text: str) -> int:
        """Parse Chinese number text to integer."""
        if text.isdigit():
            return int(text)
        return cls.CHINESE_NUMBERS.get(text, 0)


class DaysExtractor:
    """Extractor for duration information from Chinese text."""
    
    # Note: Day and night patterns are now handled directly in _extract_all_days method
    # to properly distinguish between day and night patterns for logical validation
    
    # Patterns that should return None (half day)
    HALF_DAY_PATTERNS = [r'半天', r'半日']
    
    # Maximum allowed days
    MAX_DAYS = 14
    
    def __init__(self):
        self.number_parser = ChineseNumberParser()
    
    def extract(self, text: str | None) -> Optional[int]:
        """
        Extract number of days from Chinese text.
        
        Args:
            text: Input text string
            
        Returns:
            int: Number of days (1-14) or None if no valid days found
            
        Raises:
            DaysOutOfRangeError: If days > 14
            ParseConflictError: If conflicting day specifications found
        """
        if not text or not isinstance(text, str):
            return None
        
        # Check for half day patterns first
        if self._is_half_day(text):
            return None
        
        # Extract all day matches
        found_days = self._extract_all_days(text)
        
        if not found_days:
            return None
        
        # Resolve conflicts and validate
        resolved_days = self._resolve_conflicts(found_days)
        self._validate_range(resolved_days)
        
        return resolved_days
    
    def _is_half_day(self, text: str) -> bool:
        """Check if text contains half day patterns."""
        return any(re.search(pattern, text) for pattern in self.HALF_DAY_PATTERNS)
    
    def _extract_all_days(self, text: str) -> List[int]:
        """Extract all day numbers from text."""
        day_counts = self._extract_pattern_numbers(text, r'[天日]')
        night_counts = self._extract_pattern_numbers(text, r'[晚夜]')
        
        # Check for half day/night (return empty to indicate None result)
        if self._contains_half_day(day_counts + night_counts):
            return []
        
        # Check for illogical day/night combinations
        if self._is_illogical_combination(day_counts, night_counts):
            return []
        
        return day_counts + night_counts
    
    def _extract_pattern_numbers(self, text: str, unit_pattern: str) -> List[int]:
        """Extract numbers for a specific unit pattern (天/日 or 晚/夜)."""
        number_pattern = r'(\d+|一|二|三|四|五|六|七|八|九|十|十一|十二|十三|十四|十五|十六|十七|十八|十九|二十|兩)'
        pattern = number_pattern + r'[，\s]*' + unit_pattern
        matches = re.findall(pattern, text)
        
        valid_numbers = []
        for match in matches:
            num = self.number_parser.parse(match)
            if num > 0:
                valid_numbers.append(num)
        
        return valid_numbers
    
    def _contains_half_day(self, numbers: List[int]) -> bool:
        """Check if any number represents a half day (0.5)."""
        return any(num == 0.5 for num in numbers)
    
    def _is_illogical_combination(self, day_counts: List[int], night_counts: List[int]) -> bool:
        """Check for illogical day/night combinations like '一天兩夜'."""
        if not (day_counts and night_counts):
            return False
            
        # Special case: exactly one day and exactly one night value
        if len(day_counts) == 1 and len(night_counts) == 1:
            day_val = day_counts[0]
            night_val = night_counts[0]
            # If day < night and it's a small difference, treat as illogical
            return day_val < night_val and (night_val - day_val) <= 1
        
        # For more complex cases, let _resolve_conflicts handle it
        return False
    
    def _resolve_conflicts(self, found_days: List[int]) -> int:
        """Resolve conflicts in day specifications."""
        unique_days = set(found_days)
        
        if len(unique_days) == 1:
            return found_days[0]
        
        # Allow common patterns like "兩天一夜" (2 days 1 night)
        if len(unique_days) == 2:
            sorted_days = sorted(unique_days)
            if sorted_days[1] - sorted_days[0] == 1:
                return max(found_days)  # Use the larger number (days, not nights)
        
        raise ParseConflictError(f"Conflicting day specifications found: {list(unique_days)}")
    
    def _validate_range(self, days: int) -> None:
        """Validate that days are within acceptable range."""
        if days > self.MAX_DAYS:
            raise DaysOutOfRangeError(f"Days {days} exceeds maximum of {self.MAX_DAYS}")


class FilterExtractor:
    """Extractor for filter categories from segmented tokens."""
    
    FILTER_MAPPINGS = {
        'parking': ['停車', '好停車', '停車場', '車位', '停車位'],
        'wheelchair': ['無障礙', '輪椅', '行動不便', '殘障', '無障礙設施'],
        'kids': ['親子', '兒童', '小孩', '孩子', '小朋友', '親子友善'],
        'pet': ['寵物', '狗', '貓', '毛孩', '寵物友善', '可攜帶寵物']
    }
    
    def extract(self, tokens: List[str] | None) -> List[str]:
        """
        Extract filter categories from segmented word tokens.
        
        Args:
            tokens: List of segmented words
            
        Returns:
            List[str]: List of filter categories (no duplicates, order not guaranteed)
        """
        if not tokens or not isinstance(tokens, list):
            return []
        
        # Combine tokens to catch split keywords
        text_combined = combine_tokens(tokens)
        
        # Find matching filters
        found_filters = self._find_matching_filters(tokens, text_combined)
        
        return list(found_filters)
    
    
    def _find_matching_filters(self, tokens: List[str], combined_text: str) -> Set[str]:
        """Find all matching filter categories."""
        found_filters = set()
        
        for filter_category, keywords in self.FILTER_MAPPINGS.items():
            if self._has_matching_keyword(keywords, tokens, combined_text):
                found_filters.add(filter_category)
        
        return found_filters
    
    def _has_matching_keyword(self, keywords: List[str], tokens: List[str], combined_text: str) -> bool:
        """Check if any keyword matches in tokens or combined text."""
        for keyword in keywords:
            # Check in combined text or individual tokens
            if (keyword in combined_text or 
                any(keyword in str(token) for token in tokens 
                    if token is not None and isinstance(token, (str, int)))):
                return True
        return False


class LocationExtractor:
    """Extractor for location information from query text."""
    
    # 地點關鍵詞 - 只包含城市/地區，不包含景點
    LOCATION_KEYWORDS = {
        '沖繩': '沖繩',
        '台北': '台北',
        '東京': '東京',
        '大阪': '大阪',
        '京都': '京都',
        '那霸': '沖繩',  # 那霸屬於沖繩
        'Okinawa': '沖繩'
    }
    
    def extract(self, text: str) -> Optional[str]:
        """從查詢文字中提取地點信息（城市/地區）"""
        if not text or not isinstance(text, str):
            return None
            
        for keyword, location in self.LOCATION_KEYWORDS.items():
            if keyword in text:
                return location
        
        return None


class PoiExtractor:
    """Extractor for specific POI (Point of Interest) attractions."""
    
    # 具體景點名稱列表
    POI_KEYWORDS = [
        # 沖繩景點
        '美ら海水族館', '首里城', '萬座毛', '國際通', '殘波岬', '古宇利島',
        '部瀨名海中公園', '琉球玻璃村', 'DFS', '美國村', '新都心',
        '琉球村', '今歸仁', '中城城跡', '勝連城跡', '座喜味城跡',
        '瀨底島', '水納島', '那霸機場',
        # 可以在此添加其他城市的景點
    ]
    
    def extract(self, tokens: List[str] | None) -> List[str]:
        """
        Extract specific POI names from segmented word tokens.
        
        Args:
            tokens: List of segmented words
            
        Returns:
            List[str]: List of specific POI names (no duplicates, order not guaranteed)
        """
        if not tokens or not isinstance(tokens, list):
            return []
        
        # Combine tokens to catch split keywords
        text_combined = combine_tokens(tokens)
        
        # Find matching POI attractions
        found_pois = self._find_matching_pois(tokens, text_combined)
        
        return list(found_pois)
    
    
    def _find_matching_pois(self, tokens: List[str], combined_text: str) -> Set[str]:
        """Find all matching POI attractions."""
        found_pois = set()
        
        for poi_name in self.POI_KEYWORDS:
            if self._has_matching_poi(poi_name, tokens, combined_text):
                found_pois.add(poi_name)
        
        return found_pois
    
    def _has_matching_poi(self, poi_name: str, tokens: List[str], combined_text: str) -> bool:
        """Check if a POI name matches in tokens or combined text."""
        # Check in combined text or individual tokens
        return (poi_name in combined_text or 
                any(poi_name in str(token) for token in tokens 
                    if token is not None and isinstance(token, (str, int))))


class JiebaTokenizer:
    """Tokenizer using jieba with custom dictionary support."""
    
    def __init__(self):
        self._jieba_available = self._try_import_jieba()
        self._dict_loaded = False
    
    def _try_import_jieba(self) -> bool:
        """Try to import jieba and return availability."""
        try:
            import jieba
            self._jieba = jieba
            return True
        except ImportError:
            return False
    
    def _load_custom_dict(self) -> None:
        """Load custom dictionary if available."""
        if self._dict_loaded or not self._jieba_available:
            return
        
        try:
            dict_path = os.path.join(os.path.dirname(__file__), "..", "resources", "user_dict.txt")
            if os.path.exists(dict_path):
                self._jieba.load_userdict(dict_path)
            self._dict_loaded = True
        except Exception:
            pass  # Fail silently if dictionary loading fails
    
    def tokenize(self, text: str) -> List[str]:
        """Tokenize text using jieba or fallback method."""
        if not self._jieba_available:
            return [text]  # Fallback: use whole text as single token
        
        self._load_custom_dict()
        return self._jieba.lcut(text)


class QueryParser:
    """Main parser class that combines days, filters, POI, and location extraction."""
    
    def __init__(self):
        self.days_extractor = DaysExtractor()
        self.filter_extractor = FilterExtractor()
        self.poi_extractor = PoiExtractor()
        self.location_extractor = LocationExtractor()
        self.tokenizer = JiebaTokenizer()
    
    def parse(self, text: str) -> Dict[str, any]:
        """
        Parse query text to extract days, filters, POI, and place.
        
        Args:
            text: Input query text
            
        Returns:
            dict: Dictionary containing 'days', 'filters', 'poi', and 'place' keys
        """
        try:
            # Tokenize text
            tokens = self.tokenizer.tokenize(text)
            
            # Extract all components
            extraction_result = self._extract_all_components(text, tokens)
            
            # Validate and return result
            return self._validate_and_format_result(extraction_result)
            
        except ParseError:
            # Re-raise ParseError to preserve the validation message
            raise
        except Exception:
            # Fallback: minimal parsing with raw text
            extraction_result = self._extract_all_components(text, [text])
            return self._validate_and_format_result(extraction_result)
    
    def _extract_all_components(self, text: str, tokens: List[str]) -> Dict[str, any]:
        """Extract all components from text and tokens."""
        return {
            'days': self.days_extractor.extract(text),
            'filters': self.filter_extractor.extract(tokens),
            'poi': self.poi_extractor.extract(tokens),
            'place': self.location_extractor.extract(text)
        }
    
    def _validate_and_format_result(self, extraction_result: Dict[str, any]) -> Dict[str, any]:
        """Validate and format the extraction result."""
        days = extraction_result['days']
        filters = extraction_result['filters']
        poi = extraction_result['poi']
        place = extraction_result['place']
        
        # Convert poi list to single string (first poi or empty string)
        poi_str = poi[0] if poi else ""
        
        # Validate that at least one of place or poi is present
        if place is None and not poi:
            raise ParseError("無法判斷地名或主行程")
        
        # Ensure place is always a string (use empty string if None)
        place_str = place if place is not None else ""
        
        return {
            'days': days,
            'filters': filters,
            'poi': poi_str,
            'place': place_str
        }


# Cached parser instance using lru_cache
@lru_cache(maxsize=1)
def _get_default_parser() -> QueryParser:
    """Get the default parser instance, creating it if necessary."""
    return QueryParser()


# Cache clearing function for tests
def clear_parser_cache() -> None:
    """Clear the parser cache. Useful for testing."""
    _get_default_parser.cache_clear()


# Public API functions with optional dependency injection
def extract_days(text: str | None, parser: Optional[QueryParser] = None) -> Optional[int]:
    """Extract number of days from Chinese text."""
    if parser is None:
        parser = _get_default_parser()
    return parser.days_extractor.extract(text)


def extract_filters(tokens: List[str] | None, parser: Optional[QueryParser] = None) -> List[str]:
    """Extract filter categories from segmented word tokens."""
    if parser is None:
        parser = _get_default_parser()
    return parser.filter_extractor.extract(tokens)


def extract_poi(tokens: List[str] | None, parser: Optional[QueryParser] = None) -> List[str]:
    """Extract POI categories from segmented word tokens."""
    if parser is None:
        parser = _get_default_parser()
    return parser.poi_extractor.extract(tokens)


def parse_query(text: str, parser: Optional[QueryParser] = None) -> Dict[str, any]:
    """Parse query text to extract days, filters, and POI."""
    if parser is None:
        parser = _get_default_parser()
    return parser.parse(text)


def extract_location_from_query(parsed_query: dict, original_query: str) -> str | None:
    """從解析結果和原始查詢中提取地點信息（向後兼容的包裝函數）"""
    # 為了向後兼容性，保留這個函數但使用新的 LocationExtractor
    location_extractor = LocationExtractor()
    return location_extractor.extract(original_query)