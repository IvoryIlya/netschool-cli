from datetime import datetime
from typing import List, Dict, Optional, Any
from bs4 import BeautifulSoup
import re

class Assignment:
    def __init__(self, type: str, theme: str, date: datetime, issue_date: datetime, mark: float):
        self.type = type
        self.theme = theme
        self.date = date
        self.issue_date = issue_date
        self.mark = mark

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type,
            'theme': self.theme,
            'date': self.date.isoformat() if self.date else None,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'mark': self.mark
        }

class Grades:
    def __init__(self, html_text: str, assignment_types: List[str], has_terms: bool = False):
        self.raw = html_text
        self._types = assignment_types
        self.has_terms = has_terms
        
        # Parse the HTML
        soup = BeautifulSoup(html_text, 'html.parser')
        
        # Extract date range
        date_pattern = r'(\d{1,2}\.\d{1,2}\.\d{2})'
        date_spans = soup.select(f'table td:nth-child(2) > span:nth-child({5 if has_terms else 3})')
        dates = re.findall(date_pattern, date_spans[0].text if date_spans else '')
        
        self.range = {
            'start': self._parse_date(dates[0]) if len(dates) > 0 else None,
            'end': self._parse_date(dates[1]) if len(dates) > 1 else None
        }
        
        # Extract teacher name
        teacher_span = soup.select(f'table td:nth-child(2) > span:nth-child({11 if has_terms else 9})')
        self.teacher = teacher_span[0].text.strip() if teacher_span else ""
        
        # Extract average mark
        average_mark_td = soup.select_one('.table-print tr.totals td:nth-child(3)')
        if average_mark_td:
            mark_text = average_mark_td.text.strip()
            mark_text = mark_text.replace(',', '.')
            mark_text = re.sub(r'^\D+(?=\d)', '', mark_text)
            self.average_mark = float(mark_text) if mark_text else 0.0
        else:
            self.average_mark = 0.0

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        try:
            return datetime.strptime(date_str, '%d.%m.%y')
        except (ValueError, TypeError):
            return None

    @property
    def assignments(self) -> List[Assignment]:
        assignments = []
        soup = BeautifulSoup(self.raw, 'html.parser')
        table = soup.select_one('.table-print')
        
        if not table:
            return assignments
            
        # Skip the last row (totals)
        rows = table.select('tr')[:-1]
        
        for row in rows:
            cells = row.select('td')
            if len(cells) >= 5:
                type_cell = cells[0].text.strip()
                theme_cell = cells[1].text.strip()
                date_cell = cells[2].text.strip()
                issue_date_cell = cells[3].text.strip()
                mark_cell = cells[4].text.strip()
                
                assignment = Assignment(
                    type=type_cell,
                    theme=theme_cell,
                    date=self._parse_date(date_cell),
                    issue_date=self._parse_date(issue_date_cell),
                    mark=float(mark_cell) if mark_cell else 0.0
                )
                assignments.append(assignment)
        
        return assignments

    def to_dict(self) -> Dict[str, Any]:
        return {
            'raw': self.raw,
            'range': {
                'start': self.range['start'].isoformat() if self.range['start'] else None,
                'end': self.range['end'].isoformat() if self.range['end'] else None
            },
            'teacher': self.teacher,
            'average_mark': self.average_mark,
            'assignments': [assignment.to_dict() for assignment in self.assignments]
        }
