from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
import csv
import json
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import re

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# Helper functions
def validate_donor_data(data):
    """Validate donor form data"""
    errors = []
    
    if not data['name'].strip():
        errors.append('Name is required')
    
    if not re.match(r'^[A-Za-z\s]+$', data['name']):
        errors.append('Name should contain only letters and spaces')
    
    if not data['blood_group'] in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
        errors.append('Invalid blood group')
    
    if not re.match(r'^\d{10}$', data['phone']):
        errors.append('Phone number must be 10 digits')
    
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', data['email']):
        errors.append('Invalid email address')
    
    return errors

def get_donors():
    """Get all donors from JSON file with additional processing"""
    try:
        with open('data/donors.json', 'r') as jsonfile:
            donors = json.load(jsonfile)
            # Add calculated fields
            for donor in donors:
                donor['eligible'] = is_eligible(donor)
            return donors
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_donors(donors):
    """Save donors to both JSON and CSV files"""
    # Remove calculated fields before saving
    clean_donors = []
    for donor in donors:
        clean_donor = donor.copy()
        clean_donor.pop('eligible', None)
        clean_donors.append(clean_donor)
    
    # Save to JSON
    with open('data/donors.json', 'w') as jsonfile:
        json.dump(clean_donors, jsonfile)
    
    # Save to CSV
    if clean_donors:
        with open('data/donors.csv', 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=clean_donors[0].keys())
            writer.writeheader()
            writer.writerows(clean_donors)

def is_eligible(donor):
    """Check if donor is eligible to donate based on last donation date"""
    last_donation = donor.get('last_donation')
    if not last_donation:
        return True
    
    last_date = datetime.strptime(last_donation, '%Y-%m-%d')
    return (datetime.now() - last_date).days >= 90  # 3 month cooldown

def get_blood_group_stats():
    """Get statistics by blood group"""
    donors = get_donors()
    stats = {}
    blood_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
    
    for bg in blood_groups:
        stats[bg] = {
            'count': len([d for d in donors if d['blood_group'] == bg]),
            'eligible': len([d for d in donors if d['blood_group'] == bg and d.get('eligible', True)])
        }
    return stats

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            with open('data/users.csv', 'r') as csvfile:
                users = list(csv.DictReader(csvfile))
                user = next((u for u in users if u['email'] == request.form['email']), None)
                
                if user and check_password_hash(user['password'], request.form['password']):
                    session['user_email'] = user['email']
                    session['user_name'] = user['fullname']
                    flash('Logged in successfully!', 'success')
                    return redirect(url_for('dashboard'))
                
                flash('Invalid email or password', 'danger')
        except FileNotFoundError:
            flash('No users registered yet', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Validate form data
        errors = []
        
        if request.form['password'] != request.form['confirm_password']:
            errors.append('Passwords do not match')
        
        # Check if email already exists
        try:
            with open('data/users.csv', 'r') as csvfile:
                existing_users = list(csv.DictReader(csvfile))
                if any(user['email'] == request.form['email'] for user in existing_users):
                    errors.append('Email already registered')
        except FileNotFoundError:
            pass  # First user registration
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('register.html')
        
        # Save new user to CSV
        new_user = {
            'fullname': request.form['fullname'],
            'email': request.form['email'],
            'password': generate_password_hash(request.form['password']),
            'blood_group': request.form['blood_group'],
            'phone': request.form['phone'],
            'address': request.form['address']
        }
        
        with open('data/users.csv', 'a', newline='') as csvfile:
            fieldnames = new_user.keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if csvfile.tell() == 0:  # If file is empty, write header
                writer.writeheader()
            writer.writerow(new_user)
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        flash('Please login to access the dashboard', 'warning')
        return redirect(url_for('login'))
        
    donors = get_donors()
    stats = {
        'total_donors': len(donors),
        'eligible_donors': len([d for d in donors if d.get('eligible', True)]),
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'blood_stats': get_blood_group_stats(),
        'user_name': session.get('user_name')
    }
    return render_template('dashboard.html', stats=stats)

@app.route('/add_donor', methods=['GET', 'POST'])
def add_donor():
    if request.method == 'POST':
        donor_data = {
            'name': request.form['name'],
            'blood_group': request.form['blood_group'],
            'phone': request.form['phone'],
            'email': request.form['email'],
            'address': request.form['address'],
            'registration_date': datetime.now().strftime('%Y-%m-%d')
        }
        
        errors = validate_donor_data(donor_data)
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('add_donor.html', donor=donor_data)
        
        donors = get_donors()
        donors.append(donor_data)
        save_donors(donors)
        
        flash('Donor added successfully!', 'success')
        return redirect(url_for('view_donors'))
    
    return render_template('add_donor.html')

@app.route('/view_donors')
def view_donors():
    page = int(request.args.get('page', 1))
    per_page = 10
    blood_group = request.args.get('blood_group')
    
    donors = get_donors()
    
    # Filter by blood group if specified
    if blood_group:
        donors = [d for d in donors if d['blood_group'] == blood_group]
    
    # Pagination
    total = len(donors)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = donors[start:end]
    
    return render_template('view_donors.html', 
                         donors=paginated,
                         page=page,
                         per_page=per_page,
                         total=total,
                         blood_group=blood_group)

@app.route('/edit_donor/<int:donor_id>', methods=['GET', 'POST'])
def edit_donor(donor_id):
    donors = get_donors()
    
    if donor_id < 0 or donor_id >= len(donors):
        flash('Invalid donor ID', 'danger')
        return redirect(url_for('view_donors'))
    
    if request.method == 'POST':
        updated_data = {
            'name': request.form['name'],
            'blood_group': request.form['blood_group'],
            'phone': request.form['phone'],
            'email': request.form['email'],
            'address': request.form['address'],
            'registration_date': donors[donor_id]['registration_date']
        }
        
        errors = validate_donor_data(updated_data)
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('edit_donor.html', donor=updated_data, donor_id=donor_id)
        
        donors[donor_id] = updated_data
        save_donors(donors)
        
        flash('Donor updated successfully!', 'success')
        return redirect(url_for('view_donors'))
    
    return render_template('edit_donor.html', donor=donors[donor_id], donor_id=donor_id)

@app.route('/delete_donor/<int:donor_id>')
def delete_donor(donor_id):
    donors = get_donors()
    
    try:
        if donor_id < 0 or donor_id >= len(donors):
            raise ValueError("Invalid donor ID")
            
        deleted_name = donors[donor_id]['name']
        del donors[donor_id]
        save_donors(donors)
        flash(f'Donor {deleted_name} deleted successfully!', 'success')
    except Exception as e:
        app.logger.error(f'Error deleting donor: {str(e)}')
        flash(str(e), 'danger')
    
    return redirect(url_for('view_donors'))

@app.route('/logout')
def logout():
    session.clear()  # Clear the user session
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/search_donors')
def search_donors():
    query = request.args.get('q', '').lower()
    blood_group = request.args.get('blood_group')
    eligible_only = request.args.get('eligible') == 'true'
    
    donors = get_donors()
    
    if query:
        donors = [d for d in donors if 
                 query in d['name'].lower() or 
                 query in d['blood_group'].lower() or
                 query in d['address'].lower()]
    
    if blood_group:
        donors = [d for d in donors if d['blood_group'] == blood_group]
    
    if eligible_only:
        donors = [d for d in donors if d.get('eligible', True)]
    
    return jsonify(donors)

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/support')
def support():
    return render_template('support.html')

if __name__ == '__main__':
    app.run(debug=True)
