
from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils.module_loading import import_string
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from friendship.models import Friend, FriendshipRequest
from friendship.exceptions import AlreadyExistsError, AlreadyFriendsError
from .serializers import FriendshipRequestSerializer, FriendSerializer, FriendshipRequestResponseSerializer


User = get_user_model()


REST_FRIENDSHIP = getattr(settings, "REST_FRIENDSHIP", None)
PERMISSION_CLASSES = [import_string(c)
                      for c in REST_FRIENDSHIP["PERMISSION_CLASSES"]]
USER_SERIALIZER = import_string(REST_FRIENDSHIP["USER_SERIALIZER"]) if 'USER_SERIALIZER' in REST_FRIENDSHIP else FriendSerializer

FRIENDSHIPREQUEST_SERIALIZER = import_string(REST_FRIENDSHIP["FRIENDSHIPREQUEST_SERIALIZER"]) if 'FRIENDSHIPREQUEST_SERIALIZER' in REST_FRIENDSHIP else FriendshipRequestSerializer

class FriendViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Friend model
    """
    permission_classes = PERMISSION_CLASSES
    serializer_class = USER_SERIALIZER
    friendshiprequest_serializer_class = FRIENDSHIPREQUEST_SERIALIZER
    
    lookup_field = 'pk'

    def list(self, request):
        friend_requests = Friend.objects.friends(user=request.user)
        self.queryset = friend_requests
        self.http_method_names = ['get', 'head', 'options', ]
        return Response(self.serializer_class(friend_requests, many=True).data)

    def retrieve(self, request, pk=None):
        self.queryset = Friend.objects.friends(user=request.user)
        requested_user = get_object_or_404(User, pk=pk)
        if Friend.objects.are_friends(request.user, requested_user):
            self.http_method_names = ['get', 'head', 'options', ]
            return Response(self.serializer_class(requested_user, many=False).data)
        else:
            return Response(
                {'message': "Friend relationship not found for user."},
                status.HTTP_400_BAD_REQUEST
            )

    def get_user_from_friend_data(self, data, allow_id=False):
        user_data = { }
        if 'username' in data:
            user_data['username'] = data.get('username')
        # Keep compatibility
        if 'to_user' in data:
            user_data['username'] = data.get('to_user')
        if 'email' in data:
            user_data['email'] = data.get('email')
        # Prevent lookup by id, so users cannot try to befriend every ID (while allowing to remove friendship)
        if allow_id and 'id' in data:
                user_data['id'] = data.get('id')
                
        return get_object_or_404(
            User,
            **user_data
        )

    @ action(detail=False)
    def requests(self, request):
        friend_requests = Friend.objects.unrejected_requests(user=request.user)
        self.queryset = friend_requests
        return Response(
            self.friendshiprequest_serializer_class(friend_requests, many=True).data)

    @ action(detail=False)
    def sent_requests(self, request):
        friend_requests = Friend.objects.sent_requests(user=request.user)
        self.queryset = friend_requests
        return Response(
            self.friendshiprequest_serializer_class(friend_requests, many=True).data)

    @ action(detail=False)
    def rejected_requests(self, request):
        friend_requests = Friend.objects.rejected_requests(user=request.user)
        self.queryset = friend_requests
        return Response(
            self.friendshiprequest_serializer_class(friend_requests, many=True).data)

    @ action(detail=False, methods=['post'])
    def add_friend(self, request):
        """
        Add a new friend with POST data
        - username
        - message
        """
        to_user = self.get_user_from_friend_data(request.data, allow_id=False)

        try:
            friend_obj = Friend.objects.add_friend(
                # The sender
                request.user,
                # The recipient
                to_user,
                # Message (...or empty str)
                message=request.data.get('message', '')
            )
            return Response(
                self.friendshiprequest_serializer_class(friend_obj).data,
                status.HTTP_201_CREATED
            )
        except (AlreadyExistsError, AlreadyFriendsError) as e:
            return Response(
                {"message": str(e)},
                status.HTTP_400_BAD_REQUEST
            )

    @ action(detail=False, methods=['post'])
    def remove_friend(self, request):
        """
        Deletes a friend relationship.

        The username specified in the POST data will be
        removed from the current user's friends.
        """
        to_user = self.get_user_from_friend_data(request.data, allow_id=True)

        if Friend.objects.remove_friend(request.user, to_user):
            message = 'Friend deleted.'
            status_code = status.HTTP_204_NO_CONTENT
        else:
            message = 'Friend not found.'
            status_code = status.HTTP_400_BAD_REQUEST

        return Response(
            {"message": message},
            status=status_code
        )

    @ action(detail=False,
             serializer_class=FriendshipRequestResponseSerializer,
             methods=['post'])
    def accept_request(self, request, id=None):
        """
        Accepts a friend request

        The request id specified in the URL will be accepted
        """
        id = request.data.get('id', None)
        friendship_request = get_object_or_404(
            FriendshipRequest, pk=id)

        if not friendship_request.to_user == request.user:
            return Response(
                {"message": "Request for current user not found."},
                status.HTTP_400_BAD_REQUEST
            )

        friendship_request.accept()
        return Response(
            {"message": "Request accepted, user added to friends."},
            status.HTTP_201_CREATED
        )

    @ action(detail=False,
             serializer_class=FriendshipRequestResponseSerializer,
             methods=['post'])
    def reject_request(self, request, id=None):
        """
        Rejects a friend request

        The request id specified in the URL will be rejected
        """
        id = request.data.get('id', None)
        friendship_request = get_object_or_404(
            FriendshipRequest, pk=id)
        if not friendship_request.to_user == request.user:
            return Response(
                {"message": "Request for current user not found."},
                status.HTTP_400_BAD_REQUEST
            )

        friendship_request.reject()

        return Response(
            {
                "message": "Request rejected, user NOT added to friends."
            },
            status.HTTP_201_CREATED
        )
