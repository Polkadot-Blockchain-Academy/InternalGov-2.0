import psycopg2
import time
import json
from typing import Dict, Any

class DatabaseHandler:
    def __init__(self, db_params: Dict[str, Any], logger):
        self.conn = psycopg2.connect(**db_params)
        self.ensure_tables_exist()
        self.logger = logger
        # Define the mapping for vote_ids to column names
        self.vote_options = {
            1: 'aye',
            2: 'nay',
            3: 'recuse',
            4: 'abstain'
        }
        
    def fetch_vote_counts_from_db(self, message_id: str):
        with self.conn.cursor() as cursor:
            cursor.execute("""
                SELECT aye, nay, recuse 
                FROM referenda_thread 
                WHERE thread_id = %s;
            """, (message_id,))
            result = cursor.fetchone()
            if result:
                return result
            else:
                return 0, 0, 0

    # Updated save_or_update_vote method to ensure that the thread_id exists in the referenda_thread table before inserting into users.
    def save_or_update_vote(self, referenda_id: str, user_id: str, vote_id: int, username: str):
        with self.conn.cursor() as cursor:
            try:
                # Ensure thread_id exists in referenda_thread
                cursor.execute("SELECT 1 FROM referenda_thread WHERE thread_id = %s;", (referenda_id,))
                if cursor.fetchone() is None:
                    cursor.execute("""
                        INSERT INTO referenda_thread (thread_id, aye, nay, recuse, abstain, epoch)
                        VALUES (%s, 0, 0, 0, 0, %s);
                    """, (referenda_id, int(time.time())))
                
                # Check if the user has already voted
                cursor.execute("SELECT vote_type FROM users WHERE user_id = %s AND thread_id = %s;", (str(user_id), str(referenda_id)))
                previous_vote = cursor.fetchone()
                already_voted = bool(previous_vote)

                if already_voted:
                    previous_vote = previous_vote[0]
                    if previous_vote != vote_id:
                        # Update counts based on new and old votes
                        cursor.execute("UPDATE referenda_thread SET {} = {} - 1 WHERE thread_id = %s;".format(self.vote_options[previous_vote], self.vote_options[previous_vote]), (str(referenda_id),))
                        cursor.execute("UPDATE referenda_thread SET {} = {} + 1 WHERE thread_id = %s;".format(self.vote_options[vote_id], self.vote_options[vote_id]), (str(referenda_id),))

                    # Update user's vote
                    cursor.execute("UPDATE users SET username = %s, vote_type = %s WHERE user_id = %s AND thread_id = %s;", (username, vote_id, str(user_id), str(referenda_id)))
                else:
                    # Increment new vote count
                    cursor.execute("UPDATE referenda_thread SET {} = {} + 1 WHERE thread_id = %s;".format(self.vote_options[vote_id], self.vote_options[vote_id]), (str(referenda_id),))
                    
                    # Insert new user's vote
                    cursor.execute("INSERT INTO users (user_id, username, vote_type, thread_id) VALUES (%s, %s, %s, %s);", (str(user_id), username, vote_id, str(referenda_id)))

            except Exception as e:
                self.conn.rollback()
                raise e

        self.conn.commit()
        return already_voted, previous_vote


    def ensure_tables_exist(self):
        with self.conn.cursor() as cursor:
            # Create vote_options table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vote_options (
                    vote_id INT PRIMARY KEY,
                    description TEXT
                );
            """)

            # Insert default vote options if table is empty
            cursor.execute("SELECT COUNT(*) FROM vote_options;")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO vote_options (vote_id, description) VALUES
                    (1, 'aye'),
                    (2, 'nay'),
                    (3, 'recuse'),
                    (4, 'abstain');
                """)

            # Create referenda_thread table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referenda_thread (
                    thread_id TEXT PRIMARY KEY,
                    aye INT,
                    nay INT,
                    recuse INT,
                    abstain INT,
                    epoch INT,
                    archived BOOLEAN DEFAULT FALSE
                );
            """)

            # Create users table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT,
                    username TEXT,
                    vote_type INT,
                    thread_id TEXT,
                    UNIQUE(user_id, thread_id),
                    FOREIGN KEY(thread_id) REFERENCES referenda_thread(thread_id),
                    FOREIGN KEY(vote_type) REFERENCES vote_options(vote_id)
                );
            """)

            # Create feedback_comments table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedback_comments (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    vote_type TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    comment_message_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(thread_id) REFERENCES referenda_thread(thread_id)
                );
            """)

            self.conn.commit()

    def migrate_data(self, json_file_path, archived):
        cursor = self.conn.cursor()
        
        # Read JSON data from file
        with open(json_file_path, 'r') as f:
            json_data = json.load(f)
        
        # Migrate data to PostgreSQL
        for thread_id, data in json_data.items():
            cursor.execute("""
                INSERT INTO referenda_thread (thread_id, aye, nay, recuse, epoch, archived)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (thread_id)
                DO UPDATE SET aye=EXCLUDED.aye, nay=EXCLUDED.nay, recuse=EXCLUDED.recuse, epoch=EXCLUDED.epoch, archived=%s;
            """, (thread_id, data['aye'], data['nay'], data['recuse'], data['epoch'], archived, archived))

            
            for user_id, user_data in data.get('users', {}).items():
                # Debugging print
                print(user_id, user_data.get('username'), user_data.get('vote_type'), thread_id)

                # Check for None values
                if None in [user_id, user_data.get('username'), user_data.get('vote_type'), thread_id]:
                    print("Skipping due to None value")
                    continue

                cursor.execute("""
                    INSERT INTO users (user_id, username, vote_type, thread_id)
                    VALUES (%s, %s,
                        (SELECT vote_id FROM vote_options WHERE description = %s),
                        %s)
                    ON CONFLICT (user_id, thread_id)
                    DO UPDATE SET username=EXCLUDED.username, vote_type=EXCLUDED.vote_type;
                """, (user_id, user_data['username'], user_data['vote_type'], thread_id))

        
        # Commit changes
        self.conn.commit()

    def migrated_check(self):
        # Check if data is already migrated
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referenda_thread;")
        if cursor.fetchone()[0] == 0:
            # Migrate live and archived vote data
            self.migrate_data('../data/vote_counts.json', archived=False)
            self.migrate_data('../data/archived_votes.json', archived=True)
    
    def save_comment(self, user_id: str, username: str, thread_id: str, vote_type: str, comment: str, comment_message_id: str = None):
        """Save a feedback comment to the database."""
        with self.conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO feedback_comments (user_id, username, thread_id, vote_type, comment, comment_message_id)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (str(user_id), username, str(thread_id), vote_type, comment, comment_message_id))
                self.conn.commit()
                return True
            except Exception as e:
                self.conn.rollback()
                self.logger.error(f"Error saving comment: {e}")
                raise e
    
    def get_comments_for_thread(self, thread_id: str):
        """Get all comments for a specific thread."""
        with self.conn.cursor() as cursor:
            cursor.execute("""
                SELECT user_id, username, vote_type, comment, created_at
                FROM feedback_comments
                WHERE thread_id = %s
                ORDER BY created_at ASC;
            """, (str(thread_id),))
            return cursor.fetchall()
    
    def get_comment_count_for_thread(self, thread_id: str):
        """Get the count of comments for a specific thread."""
        with self.conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM feedback_comments
                WHERE thread_id = %s;
            """, (str(thread_id),))
            result = cursor.fetchone()
            return result[0] if result else 0
            
        