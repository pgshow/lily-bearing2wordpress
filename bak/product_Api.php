<?php
require_once(dirname(__FILE__).'/wp-load.php');
header('Content-Type:text/json;charset=utf-8');

$product_id = $_GET["product_id"];
if (empty($product_id)) {
	exit('Param is empty');
}

// Find post_id by search VideoGuid
$args = array(
'post_type'=>'post',
'post_status' => 'any',
'meta_key' => 'product_id',
'meta_value' => $product_id,
);

$wp_query=new WP_Query($args);
if ( $wp_query->have_posts() ) :
	# Id already exist
    while ( $wp_query->have_posts() ) {
        $wp_query->the_post();
			$str = array(
				'exist'=>array(
							'article_id'=>get_the_id(),
							'categories'=>get_the_category(),
						),
			);
    }
else: 
	$str = array(
        'exist'=>false,
    );
	
	
endif;
$jsonencode = json_encode($str);
echo $jsonencode;
?>