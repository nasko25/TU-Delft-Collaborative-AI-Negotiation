import logging
from typing import cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds


class TemplateAgent(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self):
        super().__init__()
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self.latest_bid: Bid = None

    def notifyChange(self, info: Inform):
        """This is the entry point of all interaction with your agent after is has been initialised.

        Args:
            info (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        if isinstance(info, Settings):
            self._settings: Settings = cast(Settings, info)
            self._me = self._settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self._progress: ProgressRounds = self._settings.getProgress()

            # the profile contains the preferences of the agent over the domain
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )
        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()
        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            # execute a turn
            self._myTurn()

            # log that we advanced a turn
            self._progress = self._progress.advance()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(info, Finished):
            # terminate the agent MUST BE CALLED
            self.terminate()
        else:
            self.getReporter().log(
                logging.WARNING, "Ignoring unknown info " + str(info)
            )

    # lets the geniusweb system know what settings this agent can handle
    # leave it as it is for this course
    def getCapabilities(self) -> Capabilities:
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    # terminates the agent and its connections
    # leave it as it is for this course
    def terminate(self):
        self.getReporter().log(logging.INFO, "party is terminating:")
        super().terminate()
        if self._profile is not None:
            self._profile.close()
            self._profile = None

    #######################################################################################
    ########## THE METHODS BELOW THIS COMMENT ARE OF MAIN INTEREST TO THE COURSE ##########
    #######################################################################################

    # give a description of your agent
    def getDescription(self) -> str:
        return "Template agent for Collaborative AI course"

    # execute a turn
    def _myTurn(self):
        # check if the last received offer if the opponent is good enough
        if self._isGood(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self._findBid()
            action = Offer(self._me, bid)
            self.latest_bid = bid

        # send the action
        self.getConnection().send(action)

    # method that checks if we would agree with an offer
    def _isGood(self, bid: Bid) -> bool:
        if bid is None:
            return False

        if self.latest_bid is None:
            self.latest_bid = self.get_highest_bid()

        profile = self._profile.getProfile()


        bid_utility_sent = profile.getUtility(self.latest_bid)
        bid_utility_received = profile.getUtility(bid)

        if bid_utility_received >= 0.95 * float(bid_utility_sent):
            print("Accepted Bid-----------------------------1", bid)
            return True
        elif bid_utility_received >= 0.9 * float(bid_utility_sent):
            print("Accepted Bid-----------------------------2", bid)
            return True

        # very basic approach that accepts if the offer is valued above 0.6 and
        # 80% of the rounds towards the deadline have passed
        return False

    def _findBid(self) -> Bid:
        # compose a list of all possible bids
        domain = self._profile.getProfile().getDomain()

        issues = domain.getIssues()
        weights = []
        not_important_issues = []
        utilities = self._profile.getProfile().getUtilities()
        for issue in issues:
            weights.append(self._profile.getProfile().getWeight(issue))

        for issue in issues:
            w = self._profile.getProfile().getWeight(issue)
            if w < 0.1 * float(max(weights)):
                not_important_issues.append(issue)

        print(not_important_issues, "Not important issues")
        if self._last_received_bid is not None:
            issues = self._last_received_bid.getIssueValues()
            last_values = self.latest_bid.getIssueValues()

            bid_issues = {}
            for issue in issues:
                value = issues.get(issue)
                if float(utilities.get(issue).getUtility(value)) > 0.75 and issue in not_important_issues:
                    bid_issues[issue] = value
                else:
                    suggested_val = 0.9 * float(utilities.get(issue).getUtility(last_values.get(issue)))
                    bid_issues[issue] = self.search_for_value(suggested_val)

            print(bid_issues, "Bidding")
            bid = Bid(bid_issues)
            print("Bid utility------------", self._profile.getProfile().getUtility(bid))
        else:
            self.latest_bid = self.get_highest_bid()
            bid = self.get_highest_bid()

        return bid

    def get_highest_bid(self):
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)

        bids_with_utility = []

        for bid in all_bids:
            bids_with_utility.append((bid, self._profile.getProfile().getUtility(bid)))

        bids_with_utility = sorted(bids_with_utility, key=lambda item: -item[1])
        return bids_with_utility[0][0]

    def search_for_value(self, val):
        max_val = 1
        desired_value = ""
        utilities = self._profile.getProfile().getUtilities()
        issues = self.latest_bid.getIssueValues()
        for issue in issues:
            value = utilities.get(issue).getUtility(issues.get(issue))
            if val <= value <= max_val:
                desired_value = issues.get(issue)
                max_val = value

        return desired_value
