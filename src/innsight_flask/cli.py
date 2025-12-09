"""CLI entry point for innsight command."""

import argparse
from typing import List, Optional
import sys

# Import modules from the same package
from .config import AppConfig
from .services import AccommodationSearchService
from .recommender import Recommender
from .exceptions import GeocodeError, ParseError, ConfigurationError
from .reporter import generate_markdown_report
from .parser import parse_query


def _setup_argument_parser() -> argparse.ArgumentParser:
    """Setup and return command line argument parser."""
    parser = argparse.ArgumentParser(
        prog='innsight',
        description='innsight <query>',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('query', help='完整中文需求句')
    parser.add_argument('--markdown', action='store_true', help='以 Markdown 格式輸出結果')
    parser.add_argument('--report', action='store_true', help='生成 Markdown 報告檔案')
    return parser


def _format_text_output(gdf) -> str:
    """Format accommodations as plain text output."""
    accommodation_count = len(gdf)
    lines = [f"找到 {accommodation_count} 筆住宿"]
    
    if accommodation_count > 0:
        # Show only top 10 results, sorted by score descending
        display_df = gdf.head(10)
        for _, row in display_df.iterrows():
            name = row.get('name', 'Unknown')
            tier = row.get('tier', 0)
            lines.append(f"name: {name}, tier: {tier}")
    
    return "\n".join(lines)


def _output_results(gdf, markdown: bool = False, search_service=None) -> None:
    """Output results to stdout."""
    if markdown and search_service is not None:
        # Use Markdown formatting
        output = search_service.format_accommodations_as_markdown(gdf)
    else:
        # Use plain text formatting
        output = _format_text_output(gdf)
    
    print(output)


def _generate_report(query: str, gdf) -> str:
    """Generate markdown report file and return file path."""
    # Parse query to extract POI information
    try:
        parsed_query = parse_query(query)
        main_poi = parsed_query.get('poi', '未知景點')
    except Exception:
        # Fallback if parsing fails
        main_poi = '未知景點'
    
    # Create query dict for report
    query_dict = {"main_poi": main_poi}
    
    # Generate report
    file_path = generate_markdown_report(query_dict, gdf)
    return file_path


def _create_recommender() -> Recommender:
    """Factory function to create and configure the recommender."""
    config = AppConfig.from_env()
    search_service = AccommodationSearchService(config)
    return Recommender(search_service)


def _handle_error(exception: Exception) -> int:
    """Handle different types of exceptions with appropriate error messages."""
    if isinstance(exception, GeocodeError):
        print("找不到地點", file=sys.stderr)
    elif isinstance(exception, Exception):
        # Handle generic exceptions with Error: prefix
        if type(exception).__name__ in ('ValueError', 'ConfigurationError', 'ParseError'):
            print(str(exception), file=sys.stderr)
        else:
            print(f"Error: {exception}", file=sys.stderr)
    
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    # Setup argument parser
    parser = _setup_argument_parser()
    
    if argv is None:
        argv = sys.argv[1:]
    
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code or 0
    
    try:
        # Initialize recommender through dependency injection
        recommender = _create_recommender()
        
        # Get accommodation recommendations
        gdf = recommender.recommend(args.query)
        
        # Generate report if requested
        if args.report:
            file_path = _generate_report(args.query, gdf)
            print(f"報告已生成：{file_path}")
        
        # Output results to terminal if not generating report only, or if both options are specified
        if not args.report or args.markdown:
            _output_results(gdf, markdown=args.markdown, search_service=recommender.search_service)
        
        return 0
        
    except Exception as e:
        return _handle_error(e)


if __name__ == "__main__":
    sys.exit(main())