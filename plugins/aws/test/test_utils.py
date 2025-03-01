from resoto_plugin_aws.resources import AWSRegion
from resoto_plugin_aws.utils import arn_partition


def test_arn_partition() -> None:
    us_east_1 = AWSRegion(id="us-east-1")
    cn_north_1 = AWSRegion(id="cn-north-1")
    us_gov_east_1 = AWSRegion(id="us-gov-east-1")
    assert arn_partition(us_east_1) == "aws"
    assert arn_partition(cn_north_1) == "aws-cn"
    assert arn_partition(us_gov_east_1) == "aws-us-gov"
