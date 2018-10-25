from django_redis import get_redis_connection
from rest_framework import status, mixins
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView, RetrieveAPIView, UpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework_jwt.views import ObtainJSONWebToken

from . import serializers
from . import constants
from .models import User
from goods.models import SKU
from carts.utils import merge_cart_cookie_to_redis


# url(r'^users/$', views.UserView.as_view())
class UserView(CreateAPIView):
    """
    用户注册

    POST http://127.0.0.1:8000/users/
    请求参数：JSON/表单
        username：用户名
        password：密码
        password2：确认密码
        sms_code：短信验证码
        mobile：机号
        allow：否同意用户协议

    返回数据： JSON
        id：用户id
        username：用户名
        mobile：手机号
    """
    serializer_class = serializers.CreateUserSerializer


# url(r'^usernames/(?P<username>\w{5,20})/count/$', views.UsernameCountView.as_view())
class UsernameCountView(APIView):
    """
    用户名数量

    GET http://127.0.0.1:8000/usernames/admin/count/
    请求参数：路径参数
        username：用户名
    返回数据： JSON
        username：用户名
        count：数量
    """

    def get(self, request, username):
        """
        获取指定用户名数量
        :param request:
        :param username:
        :return:
        """

        count = User.objects.filter(username=username).count()

        data = {
            'username': username,
            'count': count
        }

        return Response(data)


# url(r'^mobiles/(?P<mobile>1[3-9]\d{9})/count/$', views.MobileCountView.as_view())
class MobileCountView(APIView):
    """
    手机号数量

    GET 127.0.0.1:8000/mobiles/13388888888/count/
    请求参数：路径参数
        mobile：手机号
    返回数据： JSON
        mobile：手机号
        count：数量
    """

    def get(self, request, mobile):
        """
        获取指定手机号数量
        """
        count = User.objects.filter(mobile=mobile).count()

        data = {
            'mobile': mobile,
            'count': count
        }

        return Response(data)



# url(r'^authorizations/$', views.UserAuthorizeView.as_view())
class UserAuthorizeView(ObtainJSONWebToken):
    """
    用户登录
    POST http://127.0.0.1:8000/authorizations/
    请求参数： JSON/表单
        username：用户名
        password：密码
    返回数据： JSON
        username：用户名
        user_id：用户id
        token：身份认证凭据
    """

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        # 如果用户登录成功，合并购物车
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            response = merge_cart_cookie_to_redis(request, user, response)

        return response

# url(r'^user/$', views.UserDetailView.as_view())
class UserDetailView(RetrieveAPIView):
    """
    用户中心个人信息

    GET 127.0.0.1:8000/user/
    请求参数： 无
    返回数据： JSON
        id：用户id
        username：用户名
        mobile：手机号
        email：email邮箱
        email_active：邮箱是否通过验证
    """
    serializer_class = serializers.UserDetailSerializer
    permission_classes = [IsAuthenticated]  # 指明必须登录认证后才能访问

    def get_object(self):
        """
        # 返回当前请求的用户
        # 在类视图对象中，可以通过类视图对象的属性获取request
        # 在django的请求request对象中，user属性表明当请请求的用户
        :return:
        """
        return self.request.user


# url(r'^email/$', views.EmailView.as_view())
# PUT 127.0.0.1:8000/email/
class EmailView(UpdateAPIView):
    serializer_class = serializers.EmailSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    # def put(self):
    #     # 获取email
    #     # 校验email
    #     # 查询user
    #     # 更新数据
    #     # 序列化返回


# url(r'^emails/verification/$', views.VerifyEmailView.as_view())
class VerifyEmailView(APIView):
    """
    邮箱验证
    """

    def get(self, request):
        # 获取token
        token = request.query_params.get('token')
        if not token:
            return Response({'message': '缺少token'}, status=status.HTTP_400_BAD_REQUEST)

        # 验证token
        user = User.check_verify_email_token(token)
        if user is None:
            return Response({'message': '链接信息无效'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            user.email_active = True
            user.save()
            return Response({'message': 'OK'})



# router.register(r'addresses', views.AddressViewSet, base_name='addresses')
# 127.0.0.1:8000/addresses/
class AddressViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, GenericViewSet):
    """
    用户地址新增与修改
    """
    serializer_class = serializers.UserAddressSerializer
    permissions = [IsAuthenticated]

    def get_queryset(self):
        return self.request.user.addresses.filter(is_deleted=False)

    # GET /addresses/
    def list(self, request, *args, **kwargs):
        """
        用户地址列表数据
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        user = self.request.user
        return Response({
            'user_id': user.id,
            'default_address_id': user.default_address_id,
            'limit': constants.USER_ADDRESS_COUNTS_LIMIT,
            'addresses': serializer.data,
        })

    # POST /addresses/
    def create(self, request, *args, **kwargs):
        """
        保存用户地址数据
        """
        # 检查用户地址数据数目不能超过上限
        count = request.user.addresses.count()
        if count >= constants.USER_ADDRESS_COUNTS_LIMIT:
            return Response({'message': '保存地址数据已达到上限'}, status=status.HTTP_400_BAD_REQUEST)

        return super().create(request, *args, **kwargs)

    # delete /addresses/<pk>/
    def destroy(self, request, *args, **kwargs):
        """
        处理删除
        """
        address = self.get_object()

        # 进行逻辑删除
        address.is_deleted = True
        address.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    # put /addresses/pk/status/
    @action(methods=['put'], detail=True)
    def status(self, request, pk=None):
        """
        设置默认地址
        """
        address = self.get_object()
        request.user.default_address = address
        request.user.save()
        return Response({'message': 'OK'}, status=status.HTTP_200_OK)

    # put /addresses/pk/title/
    # 需要请求体参数 title
    @action(methods=['put'], detail=True)
    def title(self, request, pk=None):
        """
        修改标题
        """
        address = self.get_object()
        serializer = serializers.AddressTitleSerializer(instance=address, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

# url(r'^browse_histories/$', views.UserBrowsingHistoryView.as_view())
class UserBrowsingHistoryView(CreateAPIView):
    """
    用户浏览历史记录
    请求参数：JSON 或 表单
        sku_id：商品sku 编号
    返回数据：JSON
        sku_id：商品sku 编号
    """
    serializer_class = serializers.AddUserBrowsingHistorySerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # user_id
        user_id = request.user.id

        # 查询redis  list
        redis_conn = get_redis_connection('history')
        sku_id_list = redis_conn.lrange('history_%s' % user_id, 0, constants.USER_BROWSE_HISTORY_MAX_LIMIT)

        # 数据库
        # sku_object_list = SKU.objects.filter(id__in=sku_id_list)

        skus = []
        for sku_id in sku_id_list:
            sku = SKU.objects.get(id=sku_id)
            skus.append(sku)

        # 序列化 返回
        serializer = serializers.SKUSerializer(skus, many=True)
        return Response(serializer.data)

