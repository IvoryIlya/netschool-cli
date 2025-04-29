from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Header, Footer, Button, Static, Label, Input, Select
from textual.reactive import reactive
from textual import events
import asyncio
import json
import os
import platform
from pathlib import Path
from func import get_tomorrow_assignments, main, search_schools, find_school_id
from config import get_credentials
from datetime import datetime, timedelta, date
import httpx
import socket
from netschoolapi import errors, NetSchoolAPI
from netschoolapi.schemas import Diary, Assignment

def get_config_dir():
    system = platform.system()
    
    if system == "Linux":
        # Use ~/.config/netschool-cli on Linux
        config_dir = os.path.expanduser("~/.config/netschool-cli")
    elif system == "Windows":
        # Use %APPDATA%\netschool-cli on Windows
        config_dir = os.path.join(os.environ.get("APPDATA", ""), "netschool-cli")
    else:
        # Fallback to current directory for other systems
        config_dir = os.path.join(os.getcwd(), ".config", "netschool-cli")
    
    # Create the directory if it doesn't exist
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

# Define the config file path
CONFIG_FILE = os.path.join(get_config_dir(), "config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config
        except json.JSONDecodeError:
            return None
    else:
        return None

def save_config(username, password, school):
    """Save configuration to JSON file"""
    config = {
        "username": username,
        "password": password,
        "school": school
    }
    
    # Save configuration to file
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    
    return config

class LoginScreen(Static):
    """A login screen for the application."""
    
    def __init__(self):
        super().__init__()
        self.username = ""
        self.password = ""
        self.school = ""
        self.is_first_run = load_config() is None
        self.schools = []
        self.searching = False

    def compose(self) -> ComposeResult:
        """Create child widgets for the login screen."""
        if self.is_first_run:
            yield Label("Пожалуйста, введите данные для входа в Сетевой Город:", classes="login-subtitle")
        else:
            yield Label("Введите данные для входа или нажмите 'Пропустить' для использования сохраненных данных:", classes="login-subtitle")
        
        yield Label("Имя пользователя:", classes="login-label")
        yield Input(placeholder="Введите имя пользователя", id="username-input")
        
        yield Label("Пароль:", classes="login-label")
        yield Input(placeholder="Введите пароль", password=True, id="password-input")
        
        yield Label("ID школы или название школы:", classes="login-label")
        yield Input(placeholder="Введите ID школы или название", id="school-input")
        
        with Container(classes="login-buttons"):
            yield Button("Войти", variant="primary", id="login-btn")
            if not self.is_first_run:
                yield Button("Пропустить", variant="default", id="skip-btn")
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id == "school-input":
            # Start a search for schools when the school input changes
            asyncio.create_task(self.handle_school_search(event.input.value))
    
    async def handle_school_search(self, query):
        """Handle school search and UI updates."""
        if not query or len(query) < 3:
            return
        
        self.searching = True
        try:
            # Perform the search
            self.schools = await search_schools(query)
            
            # Update the UI
            await self.update_school_selector()
        except Exception as e:
            print(f"Error searching schools: {e}")
        finally:
            self.searching = False
    
    async def update_school_selector(self):
        """Update the school selector UI."""
        # If we have a school selector, update it
        school_selector = self.query_one("#school-selector", default=None)
        if school_selector:
            school_selector.remove()
        
        if self.schools:
            # Create a selector with the found schools
            selector = Container(id="school-selector")
            selector.mount(Label("Найденные школы:", classes="login-label"))
            
            for school in self.schools[:5]:  # Limit to 5 results
                button = Button(
                    f"{school['shortName']} (ID: {school['id']})", 
                    id=f"school-{school['id']}"
                )
                selector.mount(button)
            
            self.mount(selector)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "login-btn":
            username = self.query_one("#username-input").value
            password = self.query_one("#password-input").value
            school = self.query_one("#school-input").value
            
            if username and password and school:
                # Save the credentials
                save_config(username, password, school)
                # Notify the app that login is complete
                self.app.login_complete(username, password, school)
            else:
                # Show error message
                self.app.notify("Пожалуйста, заполните все поля", severity="error")
        
        elif event.button.id == "skip-btn":
            # Load saved credentials
            config = load_config()
            if config:
                self.app.login_complete(config["username"], config["password"], config["school"])
            else:
                self.app.notify("Нет сохраненных данных для входа", severity="error")
        
        elif event.button.id.startswith("school-"):
            # A school was selected from the search results
            school_id = event.button.id.split("-")[1]
            self.query_one("#school-input").value = school_id
            
            # Remove the school selector
            school_selector = self.query_one("#school-selector", default=None)
            if school_selector:
                school_selector.remove()

class AssignmentDisplay(Static):
    def __init__(self, assignment):
        super().__init__()
        self.assignment = assignment

    def on_mount(self) -> None:
        lesson, is_duty, deadline, content, comment = self.assignment
        
        text = f"[white]{lesson}[/]\n"
        text += f"[red]Срок сдачи: {deadline}[/]\n" if is_duty else f"Срок сдачи: {deadline}\n"
        text += f"{content}\n"
        if comment:
            text += f"[italic]{comment}[/]"
        
        self.mount(Label(text))

class LessonDisplay(Static):
    def __init__(self, lesson, assignments=None):
        super().__init__()
        self.lesson = lesson
        self.assignments = assignments

    def on_mount(self) -> None:
        lesson_number, subject, room, teacher, start_time, end_time = self.lesson
        
        text = f"[bold]{lesson_number}. {subject}[/]\n"
        text += f"Время: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}\n"
        if room:
            text += f"Кабинет: {room}\n"
        if teacher:
            text += f"Учитель: {teacher}\n"
        
        # Add homework if available
        if self.assignments:
            for assignment in self.assignments:
                if assignment.type == 'Домашнее задание':
                    text += f"\n[red]Домашнее задание:[/]\n"
                    text += f"{assignment.content}\n"
                    if assignment.comment:
                        text += f"[italic]Комментарий: {assignment.comment}[/]\n"
                    text += f"Срок сдачи: {assignment.deadline.strftime('%d.%m.%Y')}\n"
                    if assignment.is_duty:
                        text += "[bold red]Внимание! Задолженность![/]\n"
        
        self.mount(Label(text))

class ErrorOverlay(Static):
    """A custom overlay for displaying error messages."""
    
    def __init__(self, title, message):
        super().__init__()
        self.title = title
        self.message = message
    
    def compose(self) -> ComposeResult:
        yield Label(f"[bold red]{self.title}[/]", classes="error-title")
        yield Label(self.message, classes="error-message")
        yield Button("OK", variant="error", id="error-ok-btn")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "error-ok-btn":
            self.remove()

class HomeworkApp(App):
    CSS = """
    Screen {
        background: transparent;
    }

    #main-container {
        width: 100%;
        height: 100%;
        padding: 1;
    }

    #assignments-container {
        width: 100%;
        height: 1fr;
        overflow-y: auto;
    }

    AssignmentDisplay {
        background: #111111;
        padding: 1;
        margin: 1;
        border: solid white;
        min-height: 5;
        width: 100%;
    }

    Button {
        margin: 1;
        border: solid white;
        background: #333333;
        color: white;
        width: 100%;
    }

    Button:hover {
        background: #555555;
    }

    #header {
        background: #333333;
        color: white;
        text-align: center;
        padding: 1;
    }

    #footer {
        background: #333333;
        color: white;
        text-align: center;
        padding: 1;
    }

    .login-title {
        text-align: center;
        padding: 1;
        color: white;
        text-style: bold;
    }

    .login-subtitle {
        text-align: center;
        padding: 1;
        color: white;
        width: 100%;
        align: center middle;
    }

    .login-label {
        padding: 1 1 0 1;
        color: white;
    }

    .login-buttons {
        width: 100%;
        align: center middle;
        padding: 1;
    }

    Input {
        margin: 0 1 1 1;
        background: #222222;
        color: white;
        border: solid white;
    }
    
    ErrorOverlay {
        background: #222222;
        border: solid red;
        padding: 1;
        width: 80%;
        height: auto;
        align: center middle;
    }
    
    .error-title {
        text-align: center;
        padding: 1;
        color: red;
        text-style: bold;
    }
    
    .error-message {
        text-align: center;
        padding: 1;
        color: white;
    }

    LessonDisplay {
        background: #111111;
        padding: 1;
        margin: 1;
        border: solid white;
        min-height: 5;
        width: 100%;
    }

    .schedule-header {
        text-align: center;
        padding: 1;
        color: white;
        text-style: bold;
    }
    """

    def __init__(self):
        super().__init__()
        self.assignments = []
        self.loading = False
        self.username = ""
        self.password = ""
        self.school = ""
        self.is_logged_in = False
        self.api = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        # Check if we have saved credentials
        config = load_config()
        if config:
            self.username = config["username"]
            self.password = config["password"]
            self.school = config["school"]
            self.is_logged_in = True
            
            # Show the main interface
            with Container(id="main-container"):
                yield Button("Показать задания на завтра", id="tomorrow-btn", variant="primary")
                yield Button("Показать все задания", id="all-btn", variant="primary")
                yield Button("Показать расписание на завтра", id="schedule-btn", variant="primary")
                yield Vertical(id="assignments-container")
        else:
            # Show the login screen
            yield LoginScreen()
        
        yield Footer()

    def login_complete(self, username, password, school):
        """Called when login is complete."""
        self.username = username
        self.password = password
        self.school = school
        self.is_logged_in = True
        
        self.query_one(LoginScreen).remove()
        
        main_container = Container(id="main-container")
        self.mount(main_container)
        
        main_container.mount(Button("Показать задания на завтра", id="tomorrow-btn", variant="primary"))
        main_container.mount(Button("Показать все задания", id="all-btn", variant="primary"))
        main_container.mount(Button("Показать расписание на завтра", id="schedule-btn", variant="primary"))
        main_container.mount(Vertical(id="assignments-container"))
        
        # Test login to verify credentials
        asyncio.create_task(self.test_login())

    async def test_login(self):
        """Test login to verify credentials."""
        try:
            # Create a temporary API instance to test login
            await self.initialize_api()
            await self.api.logout()
        except httpx.ConnectError:
            self.show_error("Ошибка подключения", "Не удалось подключиться к серверу. Проверьте подключение к интернету.")
        except socket.gaierror:
            self.show_error("Ошибка DNS", "Не удалось разрешить имя сервера. Проверьте подключение к интернету.")
        except errors.AuthError as e:
            self.show_error("Ошибка аутентификации", f"Ошибка аутентификации: {e}")
            # Remove saved credentials if they're invalid
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
        except errors.SchoolNotFoundError as e:
            self.show_error("Школа не найдена", f"Ошибка: Школа не найдена. {e}")
        except errors.NoResponseFromServer:
            self.show_error("Нет ответа от сервера", "Ошибка: Не удалось получить ответ от сервера. Попробуйте позже.")
        except httpx.HTTPStatusError as e:
            self.show_error("Ошибка HTTP", f"Ошибка HTTP: {e.response.status_code} - {e.response.reason_phrase}")
        except Exception as e:
            self.show_error("Неизвестная ошибка", f"Произошла неизвестная ошибка: {e}")

    async def initialize_api(self):
        """Initialize NetSchoolAPI instance."""
        if not self.api:
            self.api = NetSchoolAPI('https://sgo.rso23.ru/')
            await self.api.login(self.username, self.password, self.school)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "tomorrow-btn":
            asyncio.create_task(self.load_tomorrow_assignments())
        elif event.button.id == "all-btn":
            asyncio.create_task(self.load_all_assignments())
        elif event.button.id == "schedule-btn":
            asyncio.create_task(self.load_tomorrow_schedule())

    async def load_tomorrow_assignments(self):
        self.loading = True
        self.query_one("#assignments-container").remove_children()
        self.query_one("#assignments-container").mount(Label("Загрузка..."))
        
        try:
            assignments = await get_tomorrow_assignments(self.username, self.password, self.school)
            
            self.query_one("#assignments-container").remove_children()
            if assignments:
                self.query_one("#assignments-container").mount(Label(f"Найдено заданий: {len(assignments)}"))
                
                for assignment in assignments:
                    display = AssignmentDisplay(assignment)
                    self.query_one("#assignments-container").mount(display)
            else:
                self.query_one("#assignments-container").mount(Label("На завтра нет домашних заданий"))
        except httpx.ConnectError:
            self.show_error("Ошибка подключения", "Не удалось подключиться к серверу. Проверьте подключение к интернету.")
        except socket.gaierror:
            self.show_error("Ошибка DNS", "Не удалось разрешить имя сервера. Проверьте подключение к интернету.")
        except errors.AuthError as e:
            self.show_error("Ошибка аутентификации", f"Ошибка аутентификации: {e}")
        except errors.SchoolNotFoundError as e:
            self.show_error("Школа не найдена", f"Ошибка: Школа не найдена. {e}")
        except errors.NoResponseFromServer:
            self.show_error("Нет ответа от сервера", "Ошибка: Не удалось получить ответ от сервера. Попробуйте позже.")
        except httpx.HTTPStatusError as e:
            self.show_error("Ошибка HTTP", f"Ошибка HTTP: {e.response.status_code} - {e.response.reason_phrase}")
        except Exception as e:
            self.show_error("Неизвестная ошибка", f"Произошла неизвестная ошибка: {e}")
        finally:
            self.loading = False

    async def load_all_assignments(self):
        self.loading = True
        self.query_one("#assignments-container").remove_children()
        self.query_one("#assignments-container").mount(Label("Загрузка..."))
        
        try:
            assignments = await main(self.username, self.password, self.school)
            
            self.query_one("#assignments-container").remove_children()
            if assignments:
                self.query_one("#assignments-container").mount(Label(f"Найдено заданий: {len(assignments)}"))
                
                for assignment in assignments:
                    display = AssignmentDisplay(assignment)
                    self.query_one("#assignments-container").mount(display)
            else:
                self.query_one("#assignments-container").mount(Label("Нет домашних заданий"))
        except httpx.ConnectError:
            self.show_error("Ошибка подключения", "Не удалось подключиться к серверу. Проверьте подключение к интернету.")
        except socket.gaierror:
            self.show_error("Ошибка DNS", "Не удалось разрешить имя сервера. Проверьте подключение к интернету.")
        except errors.AuthError as e:
            self.show_error("Ошибка аутентификации", f"Ошибка аутентификации: {e}")
        except errors.SchoolNotFoundError as e:
            self.show_error("Школа не найдена", f"Ошибка: Школа не найдена. {e}")
        except errors.NoResponseFromServer:
            self.show_error("Нет ответа от сервера", "Ошибка: Не удалось получить ответ от сервера. Попробуйте позже.")
        except httpx.HTTPStatusError as e:
            self.show_error("Ошибка HTTP", f"Ошибка HTTP: {e.response.status_code} - {e.response.reason_phrase}")
        except Exception as e:
            self.show_error("Неизвестная ошибка", f"Произошла неизвестная ошибка: {e}")
        finally:
            self.loading = False

    async def load_tomorrow_schedule(self):
        """Load and display tomorrow's schedule with assignments."""
        self.loading = True
        self.query_one("#assignments-container").remove_children()
        self.query_one("#assignments-container").mount(Label("Загрузка расписания..."))
        
        try:
            await self.initialize_api()
            
            # Get diary data for tomorrow
            tomorrow = date.today() + timedelta(days=1)
            
            # Try to get schedule for tomorrow
            try:
                diary = await self.api.diary(start=tomorrow, end=tomorrow)
            except Exception as e:
                if "5288" in str(e):
                    # If schedule is not available for tomorrow, show a message
                    self.query_one("#assignments-container").remove_children()
                    self.query_one("#assignments-container").mount(
                        Label(f"Расписание на {tomorrow.strftime('%d.%m.%Y')} пока недоступно")
                    )
                    return
                raise e
            
            self.query_one("#assignments-container").remove_children()
            
            if diary.schedule:
                # Add date header
                self.query_one("#assignments-container").mount(
                    Label(f"[bold]Расписание на {tomorrow.strftime('%d.%m.%Y')}[/]", 
                          classes="schedule-header")
                )
                
                # Display each lesson
                for day in diary.schedule:
                    for lesson in day.lessons:
                        display = LessonDisplay(lesson)
                        self.query_one("#assignments-container").mount(display)
            else:
                self.query_one("#assignments-container").mount(
                    Label(f"На {tomorrow.strftime('%d.%m.%Y')} нет уроков")
                )
            
        except errors.AuthError as e:
            self.show_error("Ошибка аутентификации", str(e))
        except errors.SchoolNotFoundError as e:
            self.show_error("Школа не найдена", str(e))
        except httpx.ConnectError:
            self.show_error("Ошибка подключения", "Не удалось подключиться к серверу")
        except Exception as e:
            self.show_error("Ошибка", str(e))
        finally:
            self.loading = False

    def on_unmount(self) -> None:
        """Clean up when the app is closed."""
        if self.api:
            asyncio.create_task(self.api.logout())

    def show_error(self, title, message):
        """Show an error dialog."""
        self.query_one("#assignments-container").remove_children()
        self.query_one("#assignments-container").mount(Label("Произошла ошибка при загрузке заданий"))
        
        # Create and mount the error overlay
        error_overlay = ErrorOverlay(title, message)
        self.mount(error_overlay)

def sync_logout():
    try:
        with httpx.Client() as client:
            # Make a simple POST request to the logout endpoint
            response = client.post('https://sgo.rso23.ru/auth/logout')
    except Exception as e:
        print(f"Error during logout: {e}")

if __name__ == "__main__":
    app = HomeworkApp()
    app.title = "=== Домашние задания Сетевой Город (NetSchool) ==="
    app.run()

    if hasattr(app, 'action_quit') and app.action_quit:
        sync_logout()