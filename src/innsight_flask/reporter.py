"""Markdown report generation functionality."""

import os
import hashlib
from datetime import datetime
from typing import Dict, Any
import geopandas as gpd


def generate_markdown_report(query_dict: Dict[str, Any], top_df: gpd.GeoDataFrame) -> str:
    """
    Generate a markdown report file for accommodation recommendations.
    
    Args:
        query_dict: Dictionary containing query information, must have 'main_poi' key
        top_df: GeoDataFrame with top accommodation recommendations
        
    Returns:
        str: File path to the generated markdown report
    """
    # Ensure report directory exists
    report_dir = 'report'
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)
    
    # Generate filename with timestamp and hash
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M")
    
    # Create hash from query_dict and current time for uniqueness
    hash_input = f"{query_dict}_{now.isoformat()}".encode('utf-8')
    hash_code = hashlib.md5(hash_input).hexdigest()[:6]
    
    filename = f"{timestamp}_{hash_code}.md"
    file_path = os.path.join(report_dir, filename)
    
    # Generate report content
    content = _generate_report_content(query_dict, top_df)
    
    # Write file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return file_path


def _generate_report_content(query_dict: Dict[str, Any], top_df: gpd.GeoDataFrame) -> str:
    """Generate the actual markdown content for the report."""
    main_poi = query_dict.get('main_poi', '未知景點')
    
    lines = []
    
    # Main title with POI name
    lines.append(f"# {main_poi} 周邊住宿建議")
    lines.append("")
    
    # Region distribution table
    lines.append("## 區域分佈")
    lines.append("")
    tier_counts = _calculate_tier_distribution(top_df)
    lines.append("| Tier | 數量 |")
    lines.append("|------|------|")
    for tier in [3, 2, 1]:
        count = tier_counts.get(tier, 0)
        lines.append(f"| Tier {tier} | {count} |")
    lines.append("")
    
    # Top 10 recommendations table
    lines.append("## 推薦 Top 10")
    lines.append("")
    lines.append("| 分數 | 名稱 | Tier | Rating | 停車 | 無障礙 |")
    lines.append("|------|------|------|--------|------|--------|")
    
    # Display top 10 results (assuming input is already sorted)  
    for _, row in top_df.head(10).iterrows():
        score_raw = row.get('score', 0)
        # Format score to 1 decimal place
        score = f"{float(score_raw):.1f}" if score_raw is not None else "0.0"
        name = row.get('name', '未知住宿')
        tier = row.get('tier', 0)
        
        # Handle NaN rating values
        import pandas as pd
        rating_raw = row.get('rating')
        if rating_raw is None or pd.isna(rating_raw):
            rating = 'N/A'
        else:
            try:
                # Try to format as float if it's a number
                rating = f"{float(rating_raw):.1f}"
            except (ValueError, TypeError):
                rating = 'N/A'
        
        tags = row.get('tags', {})
        parking = "✅" if tags.get('parking') == 'yes' else "❌"
        wheelchair = "✅" if tags.get('wheelchair') == 'yes' else "❌"
        
        lines.append(f"| {score} | {name} | {tier} | {rating} | {parking} | {wheelchair} |")
    
    return "\n".join(lines)


def _calculate_tier_distribution(df: gpd.GeoDataFrame) -> Dict[int, int]:
    """Calculate the distribution of accommodations by tier."""
    tier_counts = {}
    if 'tier' in df.columns:
        tier_series = df['tier'].value_counts()
        for tier, count in tier_series.items():
            tier_counts[int(tier)] = int(count)
    return tier_counts