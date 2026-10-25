from aiogram.fsm.state import State, StatesGroup


class ExpenseState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_confirmation = State()
