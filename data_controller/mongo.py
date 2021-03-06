import time
from datetime import datetime
import motor.motor_asyncio
import copy

PORT = 27017
DATABASE_NAME = "haha-no-ur"

class MongoClient:
    def __init__(self):
        """
        Constructor for a MongoClient
        """
        self.client = motor.motor_asyncio.AsyncIOMotorClient("localhost", PORT)
        self.db = self.client[DATABASE_NAME]
        self.users = UserController(self)
        self.cards = CardController(self)
        self.feedback = FeedbackController(self)

    def __del__(self):
        """
        Destructor for a MongoClient.
        """
        # Close the connection to mongodb
        self.client.close()

class DatabaseController:
    """
    Class for providing a controller that performs operations on
        a mongodb database.
    """

    def __init__(self, mongo_client: MongoClient, collection: str):
        """
        Constructor for a DatabaseController.

        :param mongo_client: Mongo client used by this controller.
        """
        self._collection = mongo_client.db[collection]

class CardController(DatabaseController):
    def __init__(self, mongo_client: MongoClient):
        """
        Constructor for a UserController.

        :param mongo_client: Mongo client used by this controller.
        """
        super().__init__(mongo_client, 'cards')

    async def upsert_card(self, card: dict):
        """
        Inserts a card into the card collection if it does not exist.

        :param card: Card dictionary to insert.
        """
        card = copy.deepcopy(card)
        card['_id'] = card['id']
        del card['id']

        doc = {'_id': card['_id']}
        setCard = {'$set': card}

        await self._collection.update(doc, setCard, upsert=True)

    async def get_card(self, card_id: int) -> dict:
        """
        Gets a single card from the database.

        :param card_id: ID of card to get.

        :return: Matching card.
        """
        cards = await self.get_cards([card_id])
        if cards:
            return cards[0]
        return None

    async def get_cards(self, card_ids: list) -> list:
        """
        Gets a list of cards from the database.

        :param card_ids: List of card IDs to get.

        :return: Matching cards.
        """
        search = {'_id': {'$in': card_ids}}
        show = {
            'idol.name': 1,
            'idol.year': 1,
            'idol.main_unit': 1,
            'idol.sub_unit': 1,
            'rarity': 1,
            'attribute': 1,
            'card_image': 1,
            'card_idolized_image': 1,
            'round_card_image': 1,
            'round_card_idolized_image': 1
        }
        cursor = self._collection.find(search, show)
        return await cursor.to_list(length=10000)

    async def get_random_cards(self, filters: dict, count: int) -> list:
        """
        Gets a random list of cards.

        :param filters: Dicitonary of filters to use.
        :param count: Number of results to return.

        :return: Random list of cards.
        """
        match = {'$match': filters}
        sample = {'$sample': {'size': count}}
        cursor = self._collection.aggregate([match, sample])
        # TODO: DatabaseController coroutine for reading entire cursor.
        return await cursor.to_list(length=100)

    async def get_card_ids(self) -> list:
        """
        Gets a list of all card IDs in the datase.

        :return: List of card IDs.
        """
        return await self._collection.distinct('_id')


class UserController(DatabaseController):
    def __init__(self, mongo_client: MongoClient):
        """
        Constructor for a UserController.

        :param mongo_client: Mongo client used by this controller.
        """
        super().__init__(mongo_client, 'users')

    async def insert_user(self, user_id: str):
        """
        Insert a new user into the database.

        :param user_id: ID of new user.
        """
        await self._collection.insert_one({'_id': user_id, 'album': []})

    async def delete_user(self, user_id: str):
        """
        Delete a user from the database.

        :param user_id: ID of the user to delete.
        """
        await self._collection.delete_one({'_id': user_id})

    async def get_all_user_ids(self) -> list:
        """
        Gets a list of all user ids from the database.

        :return: List of all user ids.
        """
        return await self._collection.find().distinct('_id')

    async def find_user(self, user_id: str) -> dict:
        """
        Finds a user in the database.

        :param user_id: ID of user to find in the database.

        :return: Dictionary of found user.
        """
        return await self._collection.find_one({'_id': user_id})

    async def get_user_album(self, user_id: str) -> list:
        """
        Gets the cards album of a user.

        :param user_id: User ID of the user to query the album from.

        :return: Card album list.
        """
        # Query cards in user's album.
        user_doc = await self.find_user(user_id)
        if not user_doc:
            return []
        return user_doc['album']

    async def get_card_from_album(self, user_id: str, card_id: int) -> dict:
        """
        Gets a card from a user's album.

        :param user_id: User ID of the user to query the card from.

        :return: Card dictionary or None if card does not exist.
        """
        search_filter = {"$elemMatch": {"id": card_id}}
        cursor = self._collection.find(
            {"_id": user_id},
            {"album": search_filter}
        )
        search = await cursor.to_list(length=10000)

        if len(search) > 0 and 'album' in search[0]:
            return search[0]['album'][0]
        return None

    async def add_to_user_album(self, user_id: str, new_cards: list,
                                idolized: bool = False):
        """
        Adds a list of cards to a user's card album.

        :param user_id: User ID of the user who's album will be added to.
        :param new_cards: List of dictionaries of new cards to add.
        :param idolized: Whether the new cards being added are idolized.
        """
        for card in new_cards:
            # User does not have this card, push to album
            if not await self._user_has_card(user_id, card['_id']):
                new_card = {
                    'id': card['_id'],
                    'unidolized_count': 1,
                    'idolized_count': 0,
                    'time_aquired': int(round(time.time() * 1000))
                }

                sort = {'id': 1}
                insert_card = {'$each': [new_card], '$sort': sort}

                await self._collection.update_one(
                    {'_id': user_id},
                    {'$push': {'album': insert_card}}
                )

            # User has this card, increment count
            else:
                if idolized:
                    await self._collection.update(
                        {'_id': user_id, 'album.id': card['_id']},
                        {'$inc': {'album.$.idolized_count': 1}}
                    )
                else:
                    await self._collection.update(
                        {'_id': user_id, 'album.id': card['_id']},
                        {'$inc': {'album.$.unidolized_count': 1}}
                    )

    async def remove_from_user_album(self, user_id: str, card_id: int,
                                     idolized: bool=False,
                                     count: int=1) -> bool:
        """
        Adds a list of cards to a user's card album.

        :param user: User ID of the user who's album will be added to.
        :param new_cards: List of dictionaries of new cards to add.
        :param idolized: Whether the new cards being added are idolized.

        :return: True if a card was deleted successfully, otherwise False.
        """
        card = await self.get_card_from_album(user_id, card_id)
        if not card:
            return False

        # Get new counts.
        new_unidolized_count = card['unidolized_count']
        new_idolized_count = card['idolized_count']
        if idolized:
            new_idolized_count -= count
        else:
            new_unidolized_count -= count

        # Update values
        await self._collection.update(
            {'_id': user_id, 'album.id': card_id},
            {
                '$set': {
                    'album.$.unidolized_count': new_unidolized_count,
                    'album.$.idolized_count': new_idolized_count
                }
            }
        )
        return True

    async def _user_has_card(self, user_id: str, card_id: int) -> bool:
        search_filter = {'$elemMatch': {'id': card_id}}

        search = await self._collection.find_one(
            {'_id': user_id},
            {'album': search_filter}
        )

        return len(search.keys()) > 1


class FeedbackController(DatabaseController):
    def __init__(self, mongo_client: MongoClient):
        """
        Constructor for a FeebackController.

        :param mongo_client: Mongo client used by this controller.
        """
        super().__init__(mongo_client, 'feedback')

    async def add_feedback(self, user_id, username, message):
        """
        Insert a new feedback into the database.
        """
        print('hrlo')
        feedback = {
            'user_id': user_id,
            'username': username,
            'date': datetime.now(),
            'message': message
        }
        await self._collection.insert_one(feedback)
