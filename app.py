from dash import Dash, html, dcc, Input, Output, State, dash_table, set_props, no_update
import dash_bootstrap_components as dbc
import sqlite3

# Créer l'application Dash
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Connexion à la base de données SQLite
def get_db_connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# Calculer K en fonction du nombre de parties jouées
def get_k_factor(games_played):
    if games_played < 5:
        return 40
    elif games_played < 10:
        return 32
    elif games_played < 20:
        return 20
    else:
        return 15

# Fonction pour calculer l'ELO
def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

def calculate_elo(winner, loser, score_w, score_l):
    conn = get_db_connection()
    
    # Récupérer les ELOs actuels
    winner_elo = conn.execute('SELECT elo FROM players WHERE player_name = ?', (winner,)).fetchone()[0]
    loser_elo = conn.execute('SELECT elo FROM players WHERE player_name = ?', (loser,)).fetchone()[0]
    
    # Récupérer le nombre de parties jouées
    winner_games_played = conn.execute('SELECT n_games_played FROM players WHERE player_name = ?', (winner,)).fetchone()[0]
    loser_games_played = conn.execute('SELECT n_games_played FROM players WHERE player_name = ?', (loser,)).fetchone()[0]
    
    # Calcul de l'espérance de gain
    expected_w = expected_score(winner_elo, loser_elo)
    expected_l = expected_score(loser_elo, winner_elo)
    
    # Calcul du multiplicateur basé sur l'écart de score, avec une valeur minimale de 1
    margin_multiplier = max((score_w - score_l) / 10, 1)
    
    # Déterminer K pour chaque joueur
    K_w = get_k_factor(winner_games_played)
    K_l = get_k_factor(loser_games_played)
    
    # Calcul des nouveaux ELOs
    new_R_w = winner_elo + round(K_w * margin_multiplier * (1 - expected_w))
    new_R_l = loser_elo + round(K_l * margin_multiplier * (0 - expected_l))
    
    # Mise à jour des ELOs et du nombre de parties jouées
    conn.execute('UPDATE players SET elo = ?, n_games_played = n_games_played + 1 WHERE player_name = ?', (new_R_w, winner))
    conn.execute('UPDATE players SET elo = ?, n_games_played = n_games_played + 1 WHERE player_name = ?', (new_R_l, loser))
    conn.commit()
    conn.close()

def create_table(players):
    unordered = [{"player_name": player['player_name'], "elo": player['elo'], "n_games_played": player['n_games_played']}
                for player in players]
    return sorted(unordered, key=lambda x: x['elo'], reverse=True)

def show_alert(message, color="danger"):
    set_props("alert", dict(is_open=True, children=message, color=color))
    return no_update

# Layout de l'application
app.layout = dbc.Container([
    dbc.Alert(id="alert", is_open=False, duration=2000, color="danger", style={"position": "absolute", "top": "0px", "z-index": 9999, "width": "98vw"}),
    html.H1("ELO babyfoot GPH", style={"textAlign": "center", "margin-bottom": "10px"}),
    dbc.Row([
        dbc.Col([
            html.Label("Joueur 1"),
            dcc.Dropdown(id='player1-dropdown', options=[]),
            html.Label("Joueur 2"),
            dcc.Dropdown(id='player2-dropdown', options=[]),
        ], width=4),
        dbc.Col([
            html.Label("Score 1"),
            dbc.Input(id='score-input-player1', type='number', placeholder="Score du joueur 1", min=0, max=10, inputmode="numeric", maxlength=2),
            html.Label("Score 2"),
            dbc.Input(id='score-input-player2', type='number', placeholder="Score du joueur 2", min=0, max=10, inputmode="numeric", maxlength=2),
            dbc.Button("Confirmer", id='confirm-btn', n_clicks=0),
        ], width=4),
        dbc.Col([
            html.Label("Ajouter un joueur (max. 15 caractères)"),
            dbc.Input(id='new-player-name', type='text', placeholder="Nom du joueur", maxlength=15),
            dbc.Button("Ajouter le joueur", id='add-player-btn', n_clicks=0),
        ], width=4)
    ]),
    dbc.Row([
        dash_table.DataTable(id='players-table', 
                        columns=[{"name": col, "id": col} for col in ["player_name", "elo", "n_games_played"]], 
                        data=[], style_table={"margin-top": "50px", "overflowY": "auto", "height": "55vh"}, 
                        sort_action="native", sort_mode="single", fixed_rows={'headers': True},
                        style_header={'backgroundColor': 'var(--bs-blue)', 'color': 'white', 'fontWeight': 'bold'},
                        style_cell={'width': '33%','textOverflow': 'ellipsis','overflow': 'hidden', 'textAlign': 'center'}),
    ]),
], fluid=True)


# Récupérer la liste des joueurs de la base de données sur page load
@app.callback(
    Output('players-table', 'data'),
    Input('players-table', 'id') # dummy input pour trigger sur page load
)
def update_table_on_load(_):
    conn = get_db_connection()
    players = conn.execute('SELECT player_name, elo, n_games_played FROM players').fetchall()
    conn.close()
    return create_table(players)

@app.callback(
    Output('player1-dropdown', 'options'),
    Output('player2-dropdown', 'options'),
    Input('players-table', 'data'),
)
def update_dropdowns(data):
    player_names = [player["player_name"] for player in data]
    return player_names, player_names

# Ajouter un nouveau joueur
@app.callback(
    Output('players-table', 'data', allow_duplicate=True),
    Output("new-player-name", "value"),
    Input('add-player-btn', 'n_clicks'),
    State('new-player-name', 'value'),
    prevent_initial_call=True
)
def add_player(n_clicks, new_player_name):
    if n_clicks > 0:
        if not new_player_name:
            show_alert("Veuillez entrer un nom de joueur.")
            return no_update, no_update
            
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO players (player_name, elo, n_games_played) VALUES (?, ?, ?)', 
                            (new_player_name, 800, 0))
        except sqlite3.IntegrityError:
            show_alert("Ce joueur existe déjà."), no_update
            return no_update, no_update
        conn.commit()
        conn.close()

    # Rafraîchir les données pour afficher le tableau
    conn = get_db_connection()
    players = conn.execute('SELECT player_name, elo, n_games_played FROM players').fetchall()
    conn.close()

    show_alert(f"Le joueur {new_player_name} a été ajouté.", color="success")
    return create_table(players), None

# Mettre à jour la base de données après une partie
@app.callback(
    Output('players-table', 'data', allow_duplicate=True),
    Output("player1-dropdown", "value"),
    Output("player2-dropdown", "value"),
    Output("score-input-player1", "value"),
    Output("score-input-player2", "value"),
    Input('confirm-btn', 'n_clicks'),
    State('player1-dropdown', 'value'),
    State('player2-dropdown', 'value'),
    State('score-input-player1', 'value'),
    State('score-input-player2', 'value'),
    prevent_initial_call=True
)
def update_scores(n_clicks, player1, player2, score1, score2):
    if n_clicks > 0:
        if player1 == player2:
            show_alert("Les deux joueurs doivent être différents.")
            return no_update, no_update, no_update, no_update, no_update
        if not player1 or not player2:
            show_alert("Veuillez sélectionner deux joueurs.")
            return no_update, no_update, no_update, no_update, no_update
        if score1 is None or score2 is None:
            show_alert("Veuillez entrer deux scores.")
            return no_update, no_update, no_update, no_update, no_update
        # Validation des scores
        if score1 < 0 or score2 < 0 or score1 > 10 or score2 > 10:
            show_alert("Les scores doivent être entre 0 et 10.")
            return no_update, no_update, no_update, no_update, no_update
        
        if score1 == 10 and score2 < 10:
            calculate_elo(player1, player2, score1, score2)
        elif score2 == 10 and score1 < 10:
            calculate_elo(player2, player1, score2, score1)
        else:
            show_alert("Un des joueurs doit avoir un score de 10.")
            return no_update, no_update, no_update, no_update, no_update
    

    # Rafraîchir les données pour afficher le tableau
    conn = get_db_connection()
    players = conn.execute('SELECT player_name, elo, n_games_played FROM players').fetchall()
    conn.close()

    show_alert("Les scores ont été mis à jour.", color="success")
    return create_table(players), None, None, None, None

server = app.server

if __name__ == '__main__':
    DB = "db.sqlite"
    app.run(debug=(False if DB == "db.sqlite" else True))
