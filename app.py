from dash import Dash, html, dcc, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import sqlite3

# Créer l'application Dash
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Connexion à la base de données SQLite
def get_db_connection():
    conn = sqlite3.connect('db.sqlite')
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
    conn.execute('UPDATE players SET elo = ?, n_games_played = n_games_played + 1 WHERE player_name = ?', 
                 (max(new_R_w, 1), winner))
    conn.execute('UPDATE players SET elo = ?, n_games_played = n_games_played + 1 WHERE player_name = ?', 
                 (max(new_R_l, 1), loser))
    conn.commit()
    conn.close()

# Layout de l'application
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.Label("Joueur 1"),
            dcc.Dropdown(id='player1-dropdown', options=[]),
            html.Label("Joueur 2"),
            dcc.Dropdown(id='player2-dropdown', options=[]),
            dbc.Button("Actualiser les données", id='refresh-btn', n_clicks=0),
        ], width=4),
        dbc.Col([
            html.Label("Score 1"),
            dbc.Input(id='score-input-player1', type='number', placeholder="Score du joueur 1", min=0, max=10),
            html.Label("Score 2"),
            dbc.Input(id='score-input-player2', type='number', placeholder="Score du joueur 2", min=0, max=10),
            dbc.Button("Confirmer", id='confirm-btn', n_clicks=0),
        ], width=4),
        dbc.Col([
            html.Label("Ajouter un joueur"),
            dbc.Input(id='new-player-name', type='text', placeholder="Nom du joueur"),
            dbc.Button("Ajouter le joueur", id='add-player-btn', n_clicks=0),
        ], width=4)
    ]),
    dbc.Row([
        dash_table.DataTable(id='players-table', 
                        columns=[{"name": col, "id": col} for col in ["player_name", "elo", "n_games_played"]], 
                        data=[], style_table={"margin-top": "50px"}, sort_action="native", sort_mode="single",
),
    ])
], fluid=True)


# Récupérer la liste des joueurs de la base de données
@app.callback(
    Output('player1-dropdown', 'options'),
    Output('player2-dropdown', 'options'),
    Output('players-table', 'data'),
    Input('refresh-btn', 'n_clicks')
)
def update_dropdowns(_):
    conn = get_db_connection()
    players = conn.execute('SELECT player_name, elo, n_games_played FROM players').fetchall()
    conn.close()
    player_names = [player["player_name"] for player in players]
    table = [{"player_name": player['player_name'], "elo": player['elo'], "n_games_played": player['n_games_played']}
                for player in players]
    return player_names, player_names, table

# Ajouter un nouveau joueur
@app.callback(
    Output('players-table', 'data', allow_duplicate=True),
    Input('add-player-btn', 'n_clicks'),
    State('new-player-name', 'value'),
    prevent_initial_call=True
)
def add_player(n_clicks, new_player_name):
    if n_clicks > 0 and new_player_name:
        conn = get_db_connection()
        conn.execute('INSERT INTO players (player_name, elo, n_games_played) VALUES (?, ?, ?)', 
                        (new_player_name, 800, 0))
        conn.commit()
        conn.close()

    # Rafraîchir les données pour afficher le tableau
    conn = get_db_connection()
    players = conn.execute('SELECT player_name, elo, n_games_played FROM players').fetchall()
    conn.close()
    return [{"player_name": player['player_name'], "elo": player['elo'], "n_games_played": player['n_games_played']} 
            for player in players]

# Mettre à jour la base de données après une partie
@app.callback(
    Output('players-table', 'data', allow_duplicate=True),
    Input('confirm-btn', 'n_clicks'),
    State('player1-dropdown', 'value'),
    State('player2-dropdown', 'value'),
    State('score-input-player1', 'value'),
    State('score-input-player2', 'value'),
    prevent_initial_call=True
)
def update_scores(n_clicks, player1, player2, score1, score2):
    if n_clicks > 0 and player1 and player2 and score1 is not None and score2 is not None:
        # Validation des scores
        if score1 < 0 or score2 < 0 or score1 > 10 or score2 > 10:
            return [{"message": "Les scores doivent être entre 0 et 10."}]
        
        if score1 == 10 and score2 < 10:
            calculate_elo(player1, player2, score1, score2)
        elif score2 == 10 and score1 < 10:
            calculate_elo(player2, player1, score2, score1)
        else:
            return [{"message": "Un des joueurs doit avoir un score de 10."}]
    
    # Rafraîchir les données pour afficher le tableau
    conn = get_db_connection()
    players = conn.execute('SELECT player_name, elo, n_games_played FROM players').fetchall()
    conn.close()
    return [{"player_name": player['player_name'], "elo": player['elo'], "n_games_played": player['n_games_played']} 
            for player in players]

server = app.server

if __name__ == '__main__':
    app.run(debug=True)
