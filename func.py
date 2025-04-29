import asyncio
from netschoolapi import NetSchoolAPI
import datetime
import calendar
import requests
import httpx

async def search_schools(school_name):
    """Search for schools by name and return a list of matches."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://sgo.rso23.ru/schools/search?name={school_name}")
        if response.status_code == 200:
            return response.json()
        return []

async def find_school_id(school_name):
    """Find a school ID by name, trying different approaches."""
    # First try to convert to int if it's a numeric string
    try:
        return int(school_name)
    except ValueError:
        pass
    
    # Search for schools
    schools = await search_schools(school_name)
    
    # Try exact match first
    for school in schools:
        if school["shortName"] == school_name:
            return school["id"]
    
    # Try case-insensitive match
    for school in schools:
        if school["shortName"].lower() == school_name.lower():
            return school["id"]
    
    # Try partial match
    for school in schools:
        if school_name.lower() in school["shortName"].lower() or school["shortName"].lower() in school_name.lower():
            return school["id"]
    
    # If we found any schools, return the first one
    if schools:
        return schools[0]["id"]
    
    # If all else fails, try to use the school name as is
    return school_name

async def assign_to_lesson(assignment_id, student_id, token, api_instance):
    request = api_instance._wrapped_client.client.build_request(
        method="GET",
        url=f'student/diary/assigns/{assignment_id}',
        params={},
        json={'at': token, 'userId': student_id},
    )
    response = await api_instance._request_with_optional_relogin(
        None,
        request,
    )
    response = response.json()
    if response['isDeleted']:
        return None
    else: return response['subjectGroup']['name']

async def main(user_name, password, school_name_or_id):
    # Create a fresh API instance for each request
    api_instance = NetSchoolAPI('https://sgo.rso23.ru/')
    
    # Try to find the school ID if it's a string
    if isinstance(school_name_or_id, str):
        try:
            school_id = await find_school_id(school_name_or_id)
            school_name_or_id = school_id
        except Exception as e:
            print(f"Error finding school ID: {e}")
            # Continue with the original value
    
    await api_instance.login(
        user_name,
        password,
        school_name_or_id
    )
    token = api_instance._access_token
    studentId = api_instance._student_id
    diary = await api_instance.diary()
    days = 0
    if diary.end.month != diary.start.month:
        _, month_days = calendar.monthrange(diary.start.year, diary.start.month)
        days = diary.start.day + diary.end.day - month_days
    else:
        days = diary.end.day - diary.start.day + 1
    if not diary.schedule:
        print('На этой неделе выходные.')
        await api_instance.logout()
        return None
    schedule = diary.schedule
    today = datetime.date.today()
    tommorow = today + datetime.timedelta(days=1)
    month = datetime.date.today().month
    assignments = []
    tom_assignments = []
    assignsId = []
    ret = []
    for weekday in range(days):
        lessons = schedule[weekday].lessons
        for lesson in lessons:
            for assignment in lesson.assignments:
                if assignment.type == 'Домашнее задание' and assignment.mark is None and assignment.content.upper() != 'БЕЗ ДОМАШНЕГО ЗАДАНИЯ.' and assignment.content.upper() != 'НЕ ЗАДАНО' and (assignment.deadline > today or assignment.is_duty == True) and (assignment.deadline.month == month or diary.end.month != diary.start.month): # Checking out that it is H/W
                    assignments.append(assignment)
                    assignsId.append(assignment.id)
                    if assignment.deadline == tommorow:
                        tom_assignments.append(assignment)
                        assignments.remove(assignment)
    
    # Process tomorrow's assignments
    for hw in tom_assignments:
        asslesson = await assign_to_lesson(hw.id, studentId, token, api_instance)
        if asslesson is not None:
            asslesson = asslesson.split('/')[1]
            duty = hw.is_duty
            deadline = datetime.datetime.strftime(hw.deadline, '%d.%m (%Y)')
            content = hw.content
            comment = hw.comment if hw.comment else None
            ret.append([asslesson, duty, deadline, content, comment])
    
    # Process other assignments
    for hw in assignments:
        asslesson = await assign_to_lesson(hw.id, studentId, token, api_instance)
        if asslesson is not None:
            asslesson = asslesson.split('/')[1]
            duty = hw.is_duty
            deadline = datetime.datetime.strftime(hw.deadline, '%d.%m (%Y)')
            content = hw.content
            comment = hw.comment if hw.comment else None
            ret.append([asslesson, duty, deadline, content, comment])
    
    await api_instance.logout()
    return ret

async def get_tomorrow_assignments(user_name, password, school_name_or_id):
    all_assignments = await main(user_name, password, school_name_or_id)
    if not all_assignments:
        return []
    
    tommorow = datetime.date.today() + datetime.timedelta(days=1)
    tommorow_str = datetime.datetime.strftime(tommorow, '%d.%m (%Y)')
    
    return [assignment for assignment in all_assignments if assignment[2] == tommorow_str] 