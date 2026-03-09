from flask import Flask, render_template, request, redirect, session
import mysql.connector

app = Flask(__name__)
app.secret_key = "auction_secret_key"

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root123",
        database="auction_db"
    )

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root123",
        database="auction_db"
    )


@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE email=%s AND password=%s",
            (email, password)
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user['user_id']
            session['role'] = user['role']
            session['name'] = user['name']

            if user['role'] == 'admin':
                return redirect('/')

            elif user['role'] == 'team_owner':
                return redirect('/team_dashboard')

            elif user['role'] == 'player':
                return redirect('/player_dashboard')

        else:
            return "Invalid credentials"

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = 'player'
        player_role = request.form.get('player_role')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return "Email already registered"

        # Create user account
        cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
            (name, email, password, role)
        )
        conn.commit()

        new_user_id = cursor.lastrowid

        # Create player profile with base_price initially 0
        cursor.execute(
            """
            INSERT INTO players (name, role, base_price, status, user_id)
            VALUES (%s, %s, %s, 'PENDING', %s)
            """,
            (name, player_role, 0, new_user_id)
        )
        conn.commit()

        conn.close()
        return redirect('/login')

    return render_template('signup.html')

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Dashboard statistics
    cursor.execute("SELECT COUNT(*) AS total_teams FROM teams")
    total_teams = cursor.fetchone()['total_teams']

    cursor.execute("SELECT COUNT(*) AS total_players FROM players")
    total_players = cursor.fetchone()['total_players']

    cursor.execute("SELECT COUNT(*) AS sold_players FROM players WHERE status = 'SOLD'")
    sold_players = cursor.fetchone()['sold_players']

    cursor.execute("SELECT COUNT(*) AS pending_players FROM players WHERE status = 'PENDING'")
    pending_players = cursor.fetchone()['pending_players']

    cursor.execute("SELECT COUNT(*) AS unsold_players FROM players WHERE status = 'UNSOLD'")
    unsold_players = cursor.fetchone()['unsold_players']

    auction_over = pending_players == 0

    conn.close()

    return render_template(
        'index.html',
        total_teams=total_teams,
        total_players=total_players,
        sold_players=sold_players,
        pending_players=pending_players,
        unsold_players=unsold_players,
        auction_over=auction_over
    )


@app.route('/bid', methods=['POST'])
def bid():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect('/login')

    player_id = int(request.form['player_id'])
    team_id = int(request.form['team_id'])
    bid_price = int(request.form['bid_price'])

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get player
    cursor.execute(
        "SELECT player_id, name, base_price, status FROM players WHERE player_id = %s",
        (player_id,)
    )
    player = cursor.fetchone()

    if not player:
        conn.close()
        return "Invalid Player ID"

    # Only allow auction if player is pending
    if player['status'] != 'PENDING':
        conn.close()
        return f"Player '{player['name']}' is not available for live auction"

    # Check base price rule
    if bid_price < player['base_price']:
        conn.close()
        return "Bid price cannot be lower than base price"

    # Get team
    cursor.execute(
        "SELECT team_id, team_name, budget FROM teams WHERE team_id = %s",
        (team_id,)
    )
    team = cursor.fetchone()

    if not team:
        conn.close()
        return "Invalid Team ID"

    if team['budget'] < bid_price:
        conn.close()
        return f"Team '{team['team_name']}' does not have enough budget"

    # Update team budget
    new_budget = team['budget'] - bid_price
    cursor.execute(
        "UPDATE teams SET budget = %s WHERE team_id = %s",
        (new_budget, team_id)
    )

    # Update player
    cursor.execute(
        """
        UPDATE players
        SET status = 'SOLD',
            sold_price = %s,
            sold_team_id = %s
        WHERE player_id = %s
        """,
        (bid_price, team_id, player_id)
    )

    # Insert auction record
    cursor.execute(
    """
    INSERT INTO auction (player_id, team_id, sold_price)
    VALUES (%s, %s, %s)
    """,
    (player_id, team_id, bid_price)
)

    conn.commit()
    conn.close()

    return redirect('/next_player')

@app.route('/sold')
def sold_players():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT p.name, t.team_name, a.sold_price
        FROM auction a
        JOIN players p ON a.player_id = p.player_id
        JOIN teams t ON a.team_id = t.team_id
    """)

    sold = cursor.fetchall()
    conn.close()

@app.route('/summary')
def summary():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Get all teams
    cursor.execute("SELECT team_id, team_name, budget FROM teams")
    teams = cursor.fetchall()

    summary_data = []

    # 2. For each team, fetch purchased players
    for team in teams:
        cursor.execute("""
            SELECT p.name, p.role, a.sold_price
            FROM auction a
            JOIN players p ON a.player_id = p.player_id
            WHERE a.team_id = %s
        """, (team['team_id'],))

        players = cursor.fetchall()

        summary_data.append({
            'team_name': team['team_name'],
            'remaining_budget': team['budget'],
            'players': players
        })

    conn.close()
    return render_template('summary.html', summary_data=summary_data)

@app.route('/add-team', methods=['GET', 'POST'])
def add_team():
    if request.method == 'POST':
        team_name = request.form['team_name']
        budget = int(request.form['budget'])
        owner_name = request.form['owner_name']
        owner_email = request.form['owner_email']
        owner_password = request.form['owner_password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if owner email already exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (owner_email,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return "Owner email already registered"

        # Create team owner user
        cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
            (owner_name, owner_email, owner_password, 'team_owner')
        )
        conn.commit()

        owner_user_id = cursor.lastrowid

        # Create team and link owner
        cursor.execute(
            "INSERT INTO teams (team_name, budget, owner_user_id) VALUES (%s, %s, %s)",
            (team_name, budget, owner_user_id)
        )
        conn.commit()

        conn.close()
        return redirect('/teams')

    return render_template('add_team.html')

@app.route('/teams')
def view_teams():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT t.team_id, t.team_name, t.budget, u.name AS owner_name, u.email AS owner_email
        FROM teams t
        LEFT JOIN users u ON t.owner_user_id = u.user_id
    """)
    teams = cursor.fetchall()

    conn.close()
    return render_template('teams.html', teams=teams)

@app.route('/add-player', methods=['GET', 'POST'])
def add_player():
    if request.method == 'POST':
        name = request.form['name']
        role = request.form['role']
        base_price = int(request.form['base_price'])

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO players (name, role, base_price) VALUES (%s, %s, %s)",
            (name, role, base_price)
        )

        conn.commit()
        conn.close()

        return redirect('/players')

    return render_template('add_player.html')

@app.route('/update_base_price/<int:player_id>', methods=['POST'])
def update_base_price(player_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect('/login')

    new_base_price = int(request.form['base_price'])

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE players SET base_price = %s WHERE player_id = %s",
        (new_base_price, player_id)
    )

    conn.commit()
    conn.close()

    return redirect('/players')

@app.route('/players')
def view_players():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM players")
    players = cursor.fetchall()

    conn.close()
    return render_template('players.html', players=players)

@app.route('/player_dashboard')
def player_dashboard():
    if 'user_id' not in session or session.get('role') != 'player':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT p.*, t.team_name
        FROM players p
        LEFT JOIN teams t ON p.sold_team_id = t.team_id
        WHERE p.user_id = %s
    """, (session['user_id'],))

    player = cursor.fetchone()
    conn.close()

    return render_template('player_dashboard.html', player=player)


@app.route('/create-team-owner', methods=['GET', 'POST'])
def create_team_owner():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        team_id = int(request.form['team_id'])

        # Check if email already exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return "Email already registered"

        # Create team owner user
        cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
            (name, email, password, 'team_owner')
        )
        conn.commit()

        owner_user_id = cursor.lastrowid

        # Assign owner to selected team
        cursor.execute(
            "UPDATE teams SET owner_user_id = %s WHERE team_id = %s",
            (owner_user_id, team_id)
        )
        conn.commit()

        conn.close()
        return redirect('/teams')

    # Fetch only teams that do not already have an owner
    cursor.execute("SELECT * FROM teams WHERE owner_user_id IS NULL")
    teams = cursor.fetchall()

    conn.close()
    return render_template('create_team_owner.html', teams=teams)


@app.route('/team_dashboard')
def team_dashboard():

    if 'user_id' not in session or session.get('role') != 'team_owner':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get team assigned to logged-in owner
    cursor.execute("""
        SELECT * FROM teams
        WHERE owner_user_id = %s
    """, (session['user_id'],))

    team = cursor.fetchone()

    if not team:
        conn.close()
        return "Team not assigned."

    # Get bought players of that team
    cursor.execute("""
        SELECT name, role, sold_price
        FROM players
        WHERE sold_team_id = %s
    """, (team['team_id'],))

    players = cursor.fetchall()

    conn.close()

    return render_template('team_dashboard.html', team=team, players=players)

@app.route('/team_players')
def team_players():
    if 'user_id' not in session or session.get('role') != 'team_owner':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT player_id, name, role, base_price, status
        FROM players
        ORDER BY player_id
    """)
    players = cursor.fetchall()

    conn.close()
    return render_template('team_players.html', players=players)

    return sold


@app.route('/next_player')
def next_player():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Current pending player
    cursor.execute("""
        SELECT *
        FROM players
        WHERE status = 'PENDING'
        ORDER BY player_id
        LIMIT 1
    """)
    player = cursor.fetchone()

    # Team cards data
    cursor.execute("""
        SELECT 
            t.team_id,
            t.team_name,
            t.budget,
            COUNT(p.player_id) AS bought_count
        FROM teams t
        LEFT JOIN players p ON t.team_id = p.sold_team_id
        GROUP BY t.team_id, t.team_name, t.budget
        ORDER BY t.team_name
    """)
    teams = cursor.fetchall()

    # Auction progress
    cursor.execute("SELECT COUNT(*) AS total_players FROM players")
    total_players = cursor.fetchone()['total_players']

    cursor.execute("SELECT COUNT(*) AS completed_players FROM players WHERE status IN ('SOLD', 'UNSOLD')")
    completed_players = cursor.fetchone()['completed_players']

    conn.close()

    return render_template(
        'live_auction.html',
        player=player,
        teams=teams,
        total_players=total_players,
        completed_players=completed_players
    )
    
@app.route('/mark_unsold/<int:player_id>', methods=['POST'])
def mark_unsold(player_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT player_id, name, status FROM players WHERE player_id = %s",
        (player_id,)
    )
    player = cursor.fetchone()

    if not player:
        conn.close()
        return "Invalid Player ID"

    if player['status'] != 'PENDING':
        conn.close()
        return f"Player '{player['name']}' is not available for live auction"

    cursor.execute(
        "UPDATE players SET status = 'UNSOLD' WHERE player_id = %s",
        (player_id,)
    )

    conn.commit()
    conn.close()

    return redirect('/next_player')






if __name__ == '__main__':
    app.run(debug=True)