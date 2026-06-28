from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, Length

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Mot de passe', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Connexion')

class ContactForm(FlaskForm):
    name = StringField('Nom', validators=[DataRequired(), Length(max=120)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField('Téléphone', validators=[DataRequired(), Length(max=30)])
    service = SelectField('Service', choices=[
        ('photo-identite', 'Photos d\'identité'),
        ('portrait-studio', 'Portraits en studio'),
        ('mariage', 'Reportage mariage'),
        ('bapteme', 'Reportage baptême'),
        ('evenement', 'Événement professionnel'),
        ('tirage', 'Tirage et développement'),
        ('photobooth', 'Location borne selfie'),
        ('album', 'Album photo mariage'),
        ('autre', 'Autre')
    ], validators=[DataRequired()])
    message = TextAreaField('Message', validators=[DataRequired(), Length(max=2000)])
    submit = SubmitField('Envoyer ma demande')

class BookingForm(FlaskForm):
    name = StringField('Nom', validators=[DataRequired(), Length(max=120)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField('Téléphone', validators=[DataRequired(), Length(max=30)])
    service = SelectField('Service', choices=[
        ('photo-identite', 'Photos d\'identité'),
        ('portrait-studio', 'Portraits en studio'),
        ('mariage', 'Reportage mariage'),
        ('bapteme', 'Reportage baptême'),
        ('evenement', 'Événement professionnel'),
        ('tirage', 'Tirage et développement'),
        ('photobooth', 'Location borne selfie'),
        ('album', 'Album photo mariage'),
        ('autre', 'Autre')
    ], validators=[DataRequired()])
    requested_date = StringField('Date souhaitée', validators=[DataRequired(), Length(max=30)])
    requested_time = StringField('Heure souhaitée', validators=[DataRequired(), Length(max=30)])
    message = TextAreaField('Message', validators=[Length(max=2000)])
    submit = SubmitField('Réserver')
