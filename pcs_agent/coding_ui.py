"""Coding controls queue work; opening this page starts no engine or model."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLabel,
                            QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
                            QHBoxLayout, QMessageBox)
from .coding import NAME


class CodingPage(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        root = QVBoxLayout(self)
        title = QLabel('Write and debug Python projects')
        title.setObjectName('title')
        root.addWidget(title)
        note = QLabel('Strident writes complete project revisions, tests them in Docker, and uses failures to try up to two repairs. Python standard library projects only. Review generated code and tests before use.')
        note.setWordWrap(True)
        root.addWidget(note)
        form = QFormLayout()
        self.project = QLineEdit('my-project')
        self.project.setMaxLength(48)
        form.addRow('Project name', self.project)
        self.tokens = QSpinBox()
        self.tokens.setRange(256, 4096)
        self.tokens.setValue(max(2048, min(4096, owner.config['num_predict'])))
        form.addRow('Output tokens per attempt', self.tokens)
        self.deadline = QSpinBox()
        self.deadline.setRange(30, 300)
        self.deadline.setValue(180)
        self.deadline.setSuffix(' seconds')
        form.addRow('Coding task deadline', self.deadline)
        root.addLayout(form)
        self.request = QPlainTextEdit()
        self.request.setPlaceholderText('Example: Write a CSV expense summary grouped by category. Test empty input, invalid amounts and normal totals.')
        root.addWidget(self.request, 1)
        row = QHBoxLayout()
        check = QPushButton('Check sandbox')
        check.clicked.connect(lambda: self.owner.submit('sandbox status'))
        row.addWidget(check)
        run = QPushButton('Write, test and repair')
        run.setObjectName('primary')
        run.clicked.connect(self.generate)
        row.addWidget(run)
        test = QPushButton('Test saved project')
        test.clicked.connect(self.retest)
        row.addWidget(test)
        root.addLayout(row)
        setup = QLabel('Setup: start Docker Desktop using Linux containers. In your terminal run: docker --context default pull python:3.12-slim. Select an installed Ollama model in Settings. Projects and test reports are saved under your workspace’s Coding folder. Stop tasks from the console task queue.')
        setup.setWordWrap(True)
        root.addWidget(setup)

    def enqueue(self, command):
        config = {**self.owner.config, 'num_predict': self.tokens.value(),
                  'task_timeout': self.deadline.value()}
        self.owner.submit(command, config=config)

    def valid_project(self):
        project = self.project.text().strip()
        if not NAME.fullmatch(project):
            QMessageBox.warning(self, 'Project name', 'Use 1 to 48 letters, digits, underscores or hyphens, starting with a letter or digit.')
            return ''
        return project

    def generate(self):
        project = self.valid_project()
        request = self.request.toPlainText().strip()
        if project and request:
            self.enqueue('/code ' + project + ' ' + request)
        elif project:
            QMessageBox.warning(self, 'Describe the task', 'Describe what the Python project should do and which cases to test.')

    def retest(self):
        project = self.valid_project()
        if project:
            self.enqueue('/testcode ' + project)
